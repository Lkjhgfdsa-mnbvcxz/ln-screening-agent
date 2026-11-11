"""Business-facing conclusions and HTML contract, entirely synthetic."""
import json
import unittest
from pathlib import Path
from ln_agent import Case, Orchestrator, Policy, FixtureResearchTool
from ln_agent.policy_guard import PolicyGuard, PolicyViolation
from ln_agent.workbench.runner import WorkbenchRunner

ROOT = Path(__file__).resolve().parents[1]

def result(name, policy=None, mutate=None):
    data = json.loads((ROOT / 'examples' / name).read_text(encoding='utf8'))
    if mutate: mutate(data)
    return Orchestrator(policy or Policy(), FixtureResearchTool()).run(Case.from_dict(data))['results'][0]

class BusinessConclusions(unittest.TestCase):
    def test_exclusion_business_label_is_no_hit_not_engine_state(self):
        d = result('case_false_positive.json')['disposition']
        self.assertEqual(d['business_conclusion'], '未命中')
        self.assertEqual(d['business_conclusion_status'], 'DRAFT_NOT_APPROVED')
        self.assertIn('未命中【', d['internal_note'])

    def test_confirmed_unique_identifier_is_hit(self):
        d = result('case_true_link.json')['disposition']
        self.assertEqual(d['business_conclusion'], '命中')
        self.assertEqual(d['business_conclusion_status'], 'DRAFT_NOT_APPROVED')

    def test_critical_name_link_is_suspected_hit(self):
        d = result('case_company_critical_suspected.json')['disposition']
        self.assertEqual(d['business_conclusion'], '疑似命中')
        self.assertTrue(d['report_recommended'])
        self.assertIn('疑似命中【', d['internal_note'])

    def test_no_source_no_conclusion_not_fake_false_positive(self):
        d = result('case_company_critical_suspected.json',mutate=lambda data: data['hits'][0]['risk_event'].clear())['disposition']
        self.assertIsNone(d['business_conclusion'])
        self.assertEqual(d['business_conclusion_status'], 'NO_CONCLUSION')
        self.assertIn('证据不足', d['internal_note'])

    def test_mandatory_escalation_and_exclusion_does_not_falsely_clear(self):
        p = Policy(mandatory_compliance_categories=frozenset({'enforcement'}))
        d = result('case_false_positive.json',policy=p)['disposition']
        self.assertIsNone(d['business_conclusion'])
        self.assertTrue(d['report_recommended'])

    def test_guard_rejects_unjustified_classification(self):
        d = result('case_company_critical_suspected.json')['disposition']
        guard = PolicyGuard(Policy())
        d['business_conclusion'] = '未命中'
        with self.assertRaises(PolicyViolation): guard.validate_disposition_draft(d)

    def test_html_does_not_hero_technical_route(self):
        js = (ROOT/'ln_agent/workbench/static/app.js').read_text(encoding='utf8')
        self.assertIn('decision?.disposition?.business_conclusion',js)
        self.assertNotIn("node('small','',decision?.route || h.phase)",js)
        self.assertIn('technical-details',js)
        self.assertIn('business_conclusion',js)

    def test_api_snapshot_carries_business_result(self):
        runner = WorkbenchRunner(persist_audit=False)
        run = runner.start('company_risk')
        with run.cond:
            run.cond.wait_for(lambda:run.status!='running',timeout=10)
        self.assertEqual(run.status,'completed',run.error)
        records = run.snapshot()['decisions']
        self.assertEqual(next(iter(records.values()))['disposition']['business_conclusion'],'疑似命中')

if __name__=='__main__': unittest.main()
