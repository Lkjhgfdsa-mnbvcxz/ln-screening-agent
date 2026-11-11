"""Live local HTTP + SSE tests use synthetic fixtures only, no remote connections."""
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from ln_agent.workbench.runner import WorkbenchRunner
from ln_agent.workbench.server import WorkbenchHTTP
from ln_agent.workbench.prior import PriorDisposition, compare_prior
from ln_agent.llm_adapter import LLMConfig, LLMExtractionAdapter

class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.runner=WorkbenchRunner(audit_dir=Path(self.temp.name),persist_audit=False)
        self.srv=WorkbenchHTTP(('127.0.0.1',0),self.runner)
        self.thread=threading.Thread(target=self.srv.serve_forever,daemon=True)
        self.thread.start()
        self.url=f'http://127.0.0.1:{self.srv.server_port}'

    def tearDown(self):
        self.srv.shutdown();self.srv.server_close()
        self.thread.join(timeout=3)
        self.temp.cleanup()

    def get(self,uri):
        with urlopen(self.url+uri,timeout=10) as res:
            return res.status,res.read(),res.headers.get('Content-Type','')

    def test_html_and_registered_skills(self):
        _,body,ctype=self.get('/')
        self.assertIn(b'LN Screening',body)
        self.assertIn('text/html',ctype)
        _,js,_=self.get('/app.js')
        self.assertIn(b'EventSource',js)
        _,body,_=self.get('/api/capabilities')
        cap=json.loads(body)
        self.assertGreaterEqual(len(cap['skills']),7)
        self.assertFalse(cap['has_external_tools'])
        self.assertIn('llm',cap)
        self.assertNotIn('api_key',json.dumps(cap))

    def test_sse_and_independent_parallel_hit_events(self):
        payload=json.dumps({'case_key':'multi','workers':4}).encode()
        request=Request(self.url+'/api/runs',data=payload,headers={'Content-Type':'application/json'},method='POST')
        with urlopen(request,timeout=10) as res:
            self.assertEqual(res.status,201)
            run_id=json.load(res)['run_id']
        rec=self.runner.get(run_id)
        with rec.cond:
            rec.cond.wait_for(lambda:rec.status!='running',timeout=10)
        self.assertEqual(rec.status,'completed',rec.error)
        state=rec.snapshot()
        self.assertEqual(state['completed'],len(state['hit_ids']))
        self.assertEqual(len(state['decisions']),len(state['hit_ids']))
        kinds={e['kind'] for e in rec.events}
        self.assertTrue({'SKILL_SELECTED','POLICY_CHECK','RULE_EVALUATED',
                         'HIT_RESULT_READY','CASE_FINISHED'}.issubset(kinds))
        self.assertTrue(any(e.get('duration_ms',-1)>=0 for e in rec.events))
        started={e['hit_id'] for e in rec.events if e['kind']=='HIT_STARTED'}
        self.assertEqual(started,set(state['hit_ids']))
        before=state['elapsed_ms'];time.sleep(.02)
        self.assertEqual(before,rec.snapshot()['elapsed_ms'])
        status,body,ctype=self.get(f'/api/runs/{run_id}/events?after=0')
        self.assertEqual(status,200)
        self.assertIn('text/event-stream',ctype)
        self.assertIn(b'event: trace',body)
        self.assertIn(b'event: finished',body)
        _,body,_=self.get(f'/api/runs/{run_id}')
        self.assertEqual(json.loads(body)['status'],'completed')
        _,body,_=self.get(f'/api/runs/{run_id}/report')
        self.assertEqual(len(json.loads(body)['results']),len(state['hit_ids']))

    def test_no_arbitrary_scenario_or_origin(self):
        payload=json.dumps({'case_key':'../../secrets','workers':4}).encode()
        req=Request(self.url+'/api/runs',data=payload,headers={'Content-Type':'application/json'},method='POST')
        with self.assertRaises(HTTPError) as e:urlopen(req,timeout=3)
        self.assertEqual(e.exception.code,400)
        req=Request(self.url+'/api/runs',data=json.dumps({'case_key':'multi'}).encode(),
                    headers={'Content-Type':'application/json','Origin':'https://attacker.example'},method='POST')
        with self.assertRaises(HTTPError) as e:urlopen(req,timeout=3)
        self.assertEqual(e.exception.code,403)

    def test_existing_decision_is_not_identity_evidence(self):
        prior=PriorDisposition.from_dict({'case_id':'case','hit_id':'hit',
            'conclusion':'true_hit','reported':False,'recorded_at':'2026-01-01',
            'source_ref':'SYNTHETIC:review','verified_by_authorized_adapter':True})
        self.assertFalse(prior.verified_by_authorized_adapter)
        comparison=compare_prior(prior,{'route':'EXCLUSION_CANDIDATE'})
        self.assertEqual(comparison['comparison'],'POTENTIAL_CONFLICT_REQUIRES_SOURCE_RECHECK')
        self.assertTrue(comparison['agent_is_independent'])

class LLMInterfaceTests(unittest.TestCase):
    def test_empty_credentials_offline(self):
        cfg=LLMConfig.from_env(Path('/this/path/does/not/exist'))
        # Installation environment usually has no LN_LLM_* vars; assertion does not require that.
        self.assertIsInstance(cfg.ready(),bool)
        self.assertFalse(LLMConfig(enabled=True,base_url='http://192.168.1.2:8000/v1',model='x').ready())
        self.assertFalse(LLMConfig(enabled=True,base_url='https://example.com/v1',model='x').ready())
        self.assertTrue(LLMConfig(enabled=True,base_url='http://127.0.0.1:8000/v1',model='x').ready())

    def test_model_cannot_self_verify(self):
        fake={'choices':[{'message':{'content':json.dumps([{
            'side':'applicant','field':'acted_in_year','value':'1998',
            'origin':'official_primary','checked':True,'verification_id':'fake',
            'evidence_id':'fraud','content_verified':True,
            'extraction_verified':True,'context':'held_position'}])}}]}
        calls=[]
        client=LLMExtractionAdapter(LLMConfig(enabled=True,
              base_url='http://127.0.0.1:8000/v1',model='fake'),
              transport=lambda body:(calls.append(body) or fake))
        with self.assertRaises(PermissionError):
            client.extract_candidates('synthetic excerpt',evidence_id='trusted')
        extracted=client.extract_candidates('synthetic excerpt',evidence_id='trusted',allow_external_text=True)
        self.assertEqual(len(calls),1)
        x=extracted[0]
        self.assertEqual(x.side,'hit')
        self.assertEqual(x.origin,'model_extracted')
        self.assertFalse(x.checked)
        self.assertEqual(x.verification_id,'')
        self.assertIsNone(x.content_verified)
        self.assertEqual(x.evidence_id,'trusted:0')

if __name__=='__main__':unittest.main()
