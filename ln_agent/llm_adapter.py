"""Optional OpenAI-compatible chat-completions adapter; not part of default offline runs.

No key -> disabled. No outbound network unless explicitly opted in.
All model outputs are unverified candidates, never identity/risk dispositions.
The core agent remains deterministic when this adapter is absent.
"""
from __future__ import annotations
from dataclasses import dataclass
import ipaddress
import json
import os
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from .extraction_contract import SYSTEM_INSTRUCTION, validate_extraction
from .models import Fact

ROOT = Path(__file__).resolve().parents[1]


def _config_values(env_file: Path | None = None) -> dict[str, str]:
    """Minimal .env reader; OS environment takes priority. No interpolation or execution."""
    out: dict[str,str] = {}
    file = env_file if env_file is not None else ROOT / '.env'
    if file.is_file():
        for line in file.read_text(encoding='utf-8').splitlines():
            line=line.strip()
            if not line or line.startswith('#') or '=' not in line: continue
            key,val=line.split('=',1)
            key=key.strip(); val=val.strip().strip('"\'')
            if key.startswith('LN_LLM_'): out[key]=val
    out.update({k:v for k,v in os.environ.items() if k.startswith('LN_LLM_')})
    return out


@dataclass(frozen=True)
class LLMConfig:
    enabled: bool = False
    base_url: str = ''
    api_key: str = ''
    model: str = ''
    allow_external: bool = False
    timeout_seconds: float = 15.0

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> 'LLMConfig':
        cfg=_config_values(env_file)
        return cls(enabled=cfg.get('LN_LLM_ENABLED','').lower() in ('1','true','yes'),
                   base_url=cfg.get('LN_LLM_BASE_URL',''),
                   api_key=cfg.get('LN_LLM_API_KEY',''),
                   model=cfg.get('LN_LLM_MODEL',''),
                   allow_external=cfg.get('LN_LLM_ALLOW_EXTERNAL','').lower() in ('1','true','yes'))

    def ready(self) -> bool:
        return bool(self.enabled and self.base_url.strip() and self.model.strip()
                    and self._valid_url())

    def _valid_url(self) -> bool:
        p=urlsplit(self.base_url)
        if p.username or p.password or not p.hostname or p.query or p.fragment: return False
        if p.scheme == 'https': return self.allow_external
        if p.scheme == 'http':
            try: return ipaddress.ip_address(p.hostname).is_loopback
            except ValueError: return p.hostname.lower()=='localhost'
        return False

    def status(self) -> dict:
        # Do not expose the key or endpoint; the dashboard only displays availability.
        return {'enabled':self.enabled,'configured':self.ready(),
                'provider':'OpenAI-compatible /v1/chat/completions',
                'model':self.model if self.ready() else '',
                'used_by_default':False,
                'remote_requires_explicit_opt_in':True}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError('LLM redirect is forbidden')


class LLMExtractionAdapter:
    """Call only with approved/synthetic text, NOT real KYB data by default."""
    def __init__(self,config: LLMConfig,transport: Callable[[dict],dict] | None = None):
        self.config=config
        self.transport=transport or self._request

    def _request(self,body:dict)->dict:
        target=self.config.base_url.rstrip('/')
        if not target.endswith('/chat/completions'):
            target=target.rstrip('/') + '/chat/completions'
        raw=json.dumps(body,ensure_ascii=False).encode('utf-8')
        req=Request(target,data=raw,method='POST',headers={
            'Content-Type':'application/json',
            **({'Authorization':'Bearer '+self.config.api_key} if self.config.api_key else {})})
        opener=build_opener(_NoRedirect())
        with opener.open(req,timeout=self.config.timeout_seconds) as res:
            if res.status != 200: raise RuntimeError('LLM response not successful')
            data=res.read(1024*1024+1)
            if len(data)>1024*1024:raise ValueError('LLM response too large')
        return json.loads(data)

    def extract_candidates(self,excerpt:str,*,evidence_id:str,source_url:str='',
                           allow_external_text:bool=False)->list[Fact]:
        if not self.config.ready(): raise RuntimeError('LLM not configured; offline engine still usable')
        if not allow_external_text: raise PermissionError('Explicit allow_external_text required before sending a document excerpt')
        if not evidence_id.strip() or len(excerpt)>12000:raise ValueError('evidence_id required and excerpt <= 12000 characters')
        body={'model':self.config.model,'temperature':0,'max_tokens':800,
              'messages':[{'role':'system','content':SYSTEM_INSTRUCTION},
                          {'role':'user','content':excerpt}]}
        response=self.transport(body)
        message=response['choices'][0]['message']['content']
        if message.startswith('```'): raise ValueError('LLM must return raw JSON without fences')
        payload=json.loads(message)
        if isinstance(payload,dict):payload=payload.get('facts')
        if not isinstance(payload,list) or len(payload)>30:raise ValueError('LLM facts must be a list <= 30')
        trusted=[]
        allowed={'name','dob','birth_year','document_number','acted_in_year',
                 'position','organization','registration_number','company_name',
                 'region','address','nationality','gender'}
        for idx,fact in enumerate(payload):
            if not isinstance(fact,dict) or fact.get('field') not in allowed:
                raise ValueError('unsupported LLM fact field')
            trusted.append({'side':'hit','field':fact['field'],
                            'value':str(fact.get('value',''))[:500],
                            'evidence_id':evidence_id+':'+str(idx),
                            'origin':'model_extracted','checked':False,
                            'context':str(fact.get('context',''))[:80],
                            'source_url':source_url})
        return validate_extraction(trusted)
