"""Actual cross-condition, runtime policy and two-case acceptance tests."""
from __future__ import annotations
import json
import unittest
from pathlib import Path
from dataclasses import replace
from ln_agent import Case, Policy, Orchestrator, FixtureResearchTool
from ln_agent.risk_gate import RiskGate
from ln_agent.models import Fact, Hit
from ln_agent.policy_guard import PolicyGuard
from scripts.run_two_cases import run_pair

ROOT=Path(__file__).resolve().parents[1]

def case_with(*, category="enforcement", hit_fields=None):
    raw=json.loads((ROOT / 'examples/case_false_positive.json').read_text(encoding='utf-8'))
    raw['hits'][0]['category']=category
    if hit_fields is not None: raw['hits'][0]['facts']=hit_fields
    return Case.from_dict(raw)

class IntegrationAcceptance(unittest.TestCase):
    def test_two_case_runner(self):
        r=run_pair()
        self.assertTrue(r['assertions_passed'])
        self.assertEqual(r['cases']['strong_link']['report']['results'][0]['identity'],'strong_link')
        self.assertEqual(r['cases']['false_positive']['report']['results'][0]['identity'],'excluded_candidate')
    def test_gate_survives_sanctions_dob_candidate(self):
        d=Orchestrator(Policy(),FixtureResearchTool()).run(case_with(category='sanctions'))['results'][0]
        self.assertEqual(d['route'],'EXCLUSION_CANDIDATE')
        self.assertTrue(d['gate']['requires_manual_screening_review'])
        self.assertTrue(d['gate_final_check']['alert_preserved_after_conclusion'])
        self.assertFalse(d['exclusion_authorized'])
    def test_compliance_gate_retained_under_approved_category_demo(self):
        policy=Policy(mandatory_compliance_categories=frozenset({'sanctions'}))
        d=Orchestrator(policy,FixtureResearchTool()).run(case_with(category='sanctions'))['results'][0]
        self.assertTrue(d['gate']['compliance_escalation_required'])
        self.assertIn('COMPLIANCE_ESCALATION_REQUIRED',d['disposition_flags'])
        self.assertTrue(d['gate_final_check']['compliance_escalation_retained'])
    def test_compliance_gate_history_is_monotonic(self):
        g=RiskGate(Policy(mandatory_compliance_categories=frozenset({'sanctions'})))
        h=Hit(hit_id='X',subject_id='Y',category='sanctions')
        a=g.evaluate(h,'unresolved')
        b=g.evaluate(h,'excluded_candidate',list(a.trigger_history))
        self.assertTrue(b.compliance_escalation_required)
        self.assertGreater(len(b.trigger_history),len(a.trigger_history))
    def test_disable_dob_rule_changes_runtime(self):
        case=case_with()
        normal=Orchestrator(Policy(),FixtureResearchTool()).run(case)['results'][0]
        disabled=Orchestrator(Policy(disabled_rules=frozenset({'P02_COMPLETE_DOB'})),FixtureResearchTool()).run(case)['results'][0]
        self.assertEqual(normal['route'],'EXCLUSION_CANDIDATE')
        self.assertNotEqual(disabled['route'],'EXCLUSION_CANDIDATE')
    def test_explicit_bad_content_blocks_dob_hard(self):
        raw=json.loads((ROOT/'examples/case_false_positive.json').read_text(encoding='utf-8'))
        raw['hits'][0]['facts'][1]['content_verified']=False
        d=Orchestrator(Policy(),FixtureResearchTool()).run(Case.from_dict(raw))['results'][0]
        self.assertNotEqual(d['route'],'EXCLUSION_CANDIDATE')
    def test_explicit_bad_extraction_blocks_dob_hard(self):
        raw=json.loads((ROOT/'examples/case_false_positive.json').read_text(encoding='utf-8'))
        raw['hits'][0]['facts'][1]['extraction_verified']=False
        d=Orchestrator(Policy(),FixtureResearchTool()).run(Case.from_dict(raw))['results'][0]
        self.assertNotEqual(d['route'],'EXCLUSION_CANDIDATE')
    def test_all_five_explanations_runtime(self):
        for item in run_pair()['cases'].values():
            d=item['report']['results'][0]
            self.assertTrue(all(d['explanation'].get(k) for k in ('why_exclusion','why_continue_or_stop','why_investigation_skipped','why_suspicion','why_report')))
    def test_tool_allowlist_is_enforced(self):
        g=PolicyGuard(Policy(allowed_tool_names=frozenset()))
        skill={'allowed_research_sources':['official']}
        self.assertFalse(g.check_tool_call('fixture_research','official:x',skill,0).allowed)
    def test_hard_disposition_is_never_implemented(self):
        g=PolicyGuard(Policy())
        self.assertFalse(g.check_state_transition('LN_WRITEBACK',human_confirmed=True).allowed)
        self.assertFalse(g.check_state_transition('WHITELIST').allowed)
    def test_name_only_has_no_precision_score(self):
        raw=json.loads((ROOT/'examples/case_false_positive.json').read_text(encoding='utf-8'))
        raw['hits'][0]['facts']=[raw['hits'][0]['facts'][0]]
        d=Orchestrator(Policy(),FixtureResearchTool()).run(Case.from_dict(raw))['results'][0]
        self.assertIsNone(d['suspicion']['score'])
    def test_full_id_mismatch_not_exclusion(self):
        raw=json.loads((ROOT/'examples/case_false_positive.json').read_text(encoding='utf-8'))
        raw['subjects'][0]['facts'].append({'side':'applicant','field':'document_number','value':'SYNTHETIC-ID-A','evidence_id':'synthetic:one','origin':'kyb_verified','checked':True,'context':'CN_NATIONAL_ID'})
        raw['hits'][0]['facts']=[raw['hits'][0]['facts'][0],{'side':'hit','field':'document_number','value':'SYNTHETIC-ID-B','evidence_id':'synthetic:two','origin':'ln_structured','checked':True,'context':'CN_NATIONAL_ID'}]
        d=Orchestrator(Policy(),FixtureResearchTool()).run(Case.from_dict(raw))['results'][0]
        self.assertNotEqual(d['route'],'EXCLUSION_CANDIDATE')
        self.assertIn('DOCUMENT_DIFFERENCE_NEEDS_HISTORY_VERIFICATION',d['evidence']['data_issues'])

if __name__=='__main__': unittest.main()
