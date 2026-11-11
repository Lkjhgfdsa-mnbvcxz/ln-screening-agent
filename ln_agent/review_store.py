"""V0.5 offline SQLite reviewer ledger, decisions and explicit REOPEN.

No production authentication, e-signatures or LN writes. An actor ID is checked
against an IN-MEMORY demo allowlist; an authenticated organization identity
provider must replace that boundary before real data is used.

Each hit has its own monotonically increasing review revision. Submitted human
attestations and decisions are append-only; REOPEN renders prior decisions and
attestations historical without deleting them or accepting them in the new
revision. Not yet a resumable *mid-investigation* task scheduler.
"""
from __future__ import annotations
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator

from .document_intelligence.models import SourceDocument
from .fact_verification import ReviewAttestation, FactVerifier

REOPEN_REASONS = frozenset({"NEW_DOCUMENT", "CORRECTED_FACT", "APPLICANT_UPDATE", "SOURCE_REVISION"})

def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()

class ReviewStore:
    def __init__(self, path: str | Path, *, authorized_reviewers: frozenset[str]):
        self.path = str(path)
        self.authorized_reviewers = frozenset(authorized_reviewers)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS hit_state (
                    case_id TEXT NOT NULL, hit_id TEXT NOT NULL,
                    revision INTEGER NOT NULL CHECK(revision>=1),
                    policy_version TEXT NOT NULL,
                    input_hash TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY(case_id,hit_id)
                );
                CREATE TABLE IF NOT EXISTS attestations (
                    case_id TEXT NOT NULL, hit_id TEXT NOT NULL,
                    revision INTEGER NOT NULL, candidate_id TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL,
                    attestation_json TEXT NOT NULL, recorded_at TEXT NOT NULL,
                    PRIMARY KEY(case_id,hit_id,revision,candidate_id),
                    FOREIGN KEY(case_id,hit_id) REFERENCES hit_state(case_id,hit_id)
                );
                CREATE TABLE IF NOT EXISTS decisions (
                    case_id TEXT NOT NULL, hit_id TEXT NOT NULL,
                    revision INTEGER NOT NULL, seq INTEGER NOT NULL,
                    decision_json TEXT NOT NULL, recorded_at TEXT NOT NULL,
                    PRIMARY KEY(case_id,hit_id,revision,seq),
                    FOREIGN KEY(case_id,hit_id) REFERENCES hit_state(case_id,hit_id)
                );
                CREATE TABLE IF NOT EXISTS review_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT NOT NULL, hit_id TEXT NOT NULL,
                    revision INTEGER NOT NULL, event_type TEXT NOT NULL,
                    actor_id TEXT NOT NULL, payload_json TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL,
                    FOREIGN KEY(case_id,hit_id) REFERENCES hit_state(case_id,hit_id)
                );
                CREATE INDEX IF NOT EXISTS idx_events_hit ON review_events(case_id,hit_id,id);
                CREATE INDEX IF NOT EXISTS idx_decisions_hit ON decisions(case_id,hit_id,revision,seq);
            """)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _append(db: sqlite3.Connection, case_id: str, hit_id: str,
                revision: int, event_type: str, actor: str, payload: dict) -> str:
        row = db.execute("""SELECT event_hash FROM review_events
                         WHERE case_id=? AND hit_id=? ORDER BY id DESC LIMIT 1""",
                         (case_id, hit_id)).fetchone()
        parent = row[0] if row else "GENESIS"
        ts = _utc()
        message = _json({"case_id": case_id, "hit_id": hit_id, "revision": revision,
                         "event_type": event_type, "actor_id": actor,
                         "payload": payload, "recorded_at": ts, "previous_hash": parent})
        digest = sha256(message.encode("utf-8")).hexdigest()
        db.execute("""INSERT INTO review_events
                (case_id,hit_id,revision,event_type,actor_id,payload_json,recorded_at,previous_hash,event_hash)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (case_id,hit_id,revision,event_type,actor,_json(payload),ts,parent,digest))
        return digest

    def register_hit(self, *, case_id: str, hit_id: str, policy_version: str, input_hash: str = "") -> int:
        if not case_id or not hit_id or not policy_version:
            raise ValueError("case_id, hit_id and policy_version required")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT revision,policy_version,input_hash FROM hit_state WHERE case_id=? AND hit_id=?",
                             (case_id, hit_id)).fetchone()
            if row:
                if row["policy_version"] != policy_version:
                    raise ValueError("policy snapshot changed: REOPEN required before evaluation")
                if input_hash and row["input_hash"] and input_hash != row["input_hash"]:
                    raise ValueError("case/hit input changed: REOPEN required before evaluation")
                if input_hash and not row["input_hash"]:
                    db.execute("UPDATE hit_state SET input_hash=? WHERE case_id=? AND hit_id=?",
                               (input_hash,case_id,hit_id))
                    self._append(db,case_id,hit_id,row["revision"],"INPUT_SNAPSHOT_BOUND","SYSTEM",
                                 {"input_hash":input_hash})
                return row["revision"]
            db.execute("INSERT INTO hit_state(case_id,hit_id,revision,policy_version,input_hash) VALUES(?,?,1,?,?)", (case_id,hit_id,policy_version,input_hash))
            self._append(db,case_id,hit_id,1,"HIT_REGISTERED","SYSTEM",{"policy_version":policy_version,"input_hash":input_hash})
            return 1

    def revision(self, case_id: str, hit_id: str) -> int:
        with self._connect() as db:
            row = db.execute("SELECT revision FROM hit_state WHERE case_id=? AND hit_id=?",
                             (case_id,hit_id)).fetchone()
            if not row: raise KeyError("unknown case/hit")
            return row["revision"]

    def submit_review(self, *, case_id: str, hit_id: str,
                      attestation: ReviewAttestation,
                      document: SourceDocument, packet: dict[str, Any]) -> dict:
        if (attestation.case_id, attestation.hit_id) != (case_id,hit_id):
            raise ValueError("review is not scoped to this case/hit")
        if attestation.reviewer_id not in self.authorized_reviewers:
            raise PermissionError("reviewer is not authorized in this demo")
        # Validate against exact parsed bytes and cited text before persistence.
        out = FactVerifier(attestations=[attestation],
                           authorized_reviewers=self.authorized_reviewers).verify_packet(
                           case_id=case_id, hit_id=hit_id, document=document, packet=packet)
        verified = [x for x in out.verification_records
                    if x["candidate_id"] == attestation.candidate_id and
                    x["status"] == "VERIFIED_FOR_COMPARISON"]
        if len(verified) != 1:
            raise ValueError("review failed provenance, attribution or coverage checks")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT revision FROM hit_state WHERE case_id=? AND hit_id=?",
                             (case_id,hit_id)).fetchone()
            if not row: raise KeyError("register case/hit before submitting")
            rev = row["revision"]
            db.execute("""INSERT INTO attestations
                 (case_id,hit_id,revision,candidate_id,source_sha256,attestation_json,recorded_at)
                 VALUES(?,?,?,?,?,?,?)""",
                 (case_id,hit_id,rev,attestation.candidate_id,attestation.source_sha256,
                  _json(asdict(attestation)),_utc()))
            self._append(db,case_id,hit_id,rev,"HUMAN_REVIEW_ACCEPTED",attestation.reviewer_id,
                         {"candidate_id":attestation.candidate_id,"source_sha256":attestation.source_sha256,
                          "verification_id":verified[0]["verification_id"],
                          "claim_id":attestation.claim_id,
                          "source_origin_id":attestation.source_origin_id})
            return {"revision":rev,"verification":verified[0]}

    def active_attestations(self, case_id: str, hit_id: str) -> list[ReviewAttestation]:
        with self._connect() as db:
            revrow = db.execute("SELECT revision FROM hit_state WHERE case_id=? AND hit_id=?",
                                (case_id,hit_id)).fetchone()
            if not revrow: raise KeyError("unknown case/hit")
            rows = db.execute("""SELECT attestation_json FROM attestations
                         WHERE case_id=? AND hit_id=? AND revision=? ORDER BY candidate_id""",
                         (case_id,hit_id,revrow["revision"])).fetchall()
            return [ReviewAttestation.from_dict(json.loads(row[0])) for row in rows]

    def save_decision(self, *, case_id: str, hit_id: str, decision: dict,
                      actor_id: str = "SYSTEM") -> tuple[int, int]:
        if decision.get("hit_id") != hit_id:
            raise ValueError("decision must belong to given hit")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT revision FROM hit_state WHERE case_id=? AND hit_id=?",
                             (case_id,hit_id)).fetchone()
            if not row: raise KeyError("unknown case/hit")
            rev = row["revision"]
            seq = db.execute("""SELECT COALESCE(MAX(seq),0)+1 FROM decisions
                         WHERE case_id=? AND hit_id=? AND revision=?""",
                         (case_id,hit_id,rev)).fetchone()[0]
            db.execute("INSERT INTO decisions VALUES(?,?,?,?,?,?)",
                       (case_id,hit_id,rev,seq,_json(decision),_utc()))
            self._append(db,case_id,hit_id,rev,"DECISION_SNAPSHOT",actor_id,
                         {"route":decision.get("route"),"seq":seq,
                          "disposition_flags":decision.get("disposition_flags",[])})
            return rev, seq

    def reopen(self, *, case_id: str, hit_id: str, reviewer_id: str,
               reason: str, new_material_refs: list[str],
               new_policy_version: str | None = None) -> int:
        if reviewer_id not in self.authorized_reviewers:
            raise PermissionError("REOPEN requires authorized human")
        if reason not in REOPEN_REASONS:
            raise ValueError("REOPEN reason must be an approved enum")
        if not new_material_refs or not all(x and isinstance(x,str) for x in new_material_refs):
            raise ValueError("REOPEN needs explicit nonempty new material references")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT revision,policy_version FROM hit_state WHERE case_id=? AND hit_id=?",
                           (case_id,hit_id)).fetchone()
            if not row:raise KeyError("unknown case/hit")
            rev = row["revision"] + 1
            policy = new_policy_version or row["policy_version"]
            db.execute("UPDATE hit_state SET revision=?,policy_version=?,input_hash='' WHERE case_id=? AND hit_id=?",
                       (rev,policy,case_id,hit_id))
            self._append(db,case_id,hit_id,rev,"REOPEN",reviewer_id,
                         {"previous_revision":rev-1,"reason":reason,
                          "new_material_refs":new_material_refs,
                          "old_attestations_inactive":True,"old_decisions_historical":True,
                          "policy_version":policy})
            return rev

    def decisions(self, case_id: str, hit_id: str) -> list[dict]:
        current = self.revision(case_id,hit_id)
        with self._connect() as db:
            rows=db.execute("""SELECT revision,seq,decision_json,recorded_at FROM decisions
                       WHERE case_id=? AND hit_id=? ORDER BY revision,seq""",
                       (case_id,hit_id)).fetchall()
            return [{"revision":r["revision"],"seq":r["seq"],"recorded_at":r["recorded_at"],
                     "historical":r["revision"]<current,"decision":json.loads(r["decision_json"])}
                    for r in rows]

    def event_log(self, case_id: str, hit_id: str) -> list[dict]:
        with self._connect() as db:
            rows=db.execute("""SELECT * FROM review_events WHERE case_id=? AND hit_id=? ORDER BY id""",
                            (case_id,hit_id)).fetchall()
            return [dict(r)|{"payload":json.loads(r["payload_json"])} for r in rows]

    def verify_local_audit_chain(self, case_id: str, hit_id: str) -> bool:
        parent="GENESIS"
        for row in self.event_log(case_id,hit_id):
            payload = {"case_id": row["case_id"],"hit_id":row["hit_id"],
                       "revision":row["revision"],"event_type":row["event_type"],
                       "actor_id":row["actor_id"],"payload":row["payload"],
                       "recorded_at":row["recorded_at"],"previous_hash":parent}
            digest=sha256(_json(payload).encode("utf-8")).hexdigest()
            if row["previous_hash"]!=parent or row["event_hash"]!=digest:
                return False
            parent=digest
        return True

    def backup(self, destination: str | Path) -> None:
        """WAL-consistent SQLite online backup; no raw .db file copy."""
        target=Path(destination)
        target.parent.mkdir(parents=True,exist_ok=True)
        with self._connect() as source, sqlite3.connect(str(target)) as dest:
            source.backup(dest)
