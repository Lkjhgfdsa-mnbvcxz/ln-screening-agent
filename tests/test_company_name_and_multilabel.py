"""Regression tests motivated by a private-case failure; only SYNTHETIC data."""
import copy
import json
from pathlib import Path
import unittest
from ln_agent import Case, Orchestrator, Policy, FixtureResearchTool
from ln_agent.evidence import norm, evaluate
from ln_agent.name_matching import normalize_company_name, company_name_match_kind
from ln_agent.risk_categories import risk_categories

ROOT=Path(__file__).resolve().parents[1]

def run_case(mutate=None, policy=None):
    data=json.loads((ROOT/'examples'/'case_company_critical_suspected.json').read_text(encoding='utf-8'))
    if mutate: mutate(data)
    return Orchestrator(policy or Policy(), FixtureResearchTool()).run(Case.from_dict(data))['results'][0]

class TestCompanyNameAndRiskCategories(unittest.TestCase):
    def test_ltd_limited_company_equivalent_is_soft(self):
        def mutate(d):
            d['subjects'][0]['facts'][0]['value']='MOCK NOVA SEMICONDUCTOR CO., LIMITED'
            d['hits'][0]['facts'][0]['value']='MOCK NOVA SEMICONDUCTOR CO., LTD.'
        r=run_case(mutate)
        self.assertIn('name_exact',r['evidence']['soft_signals'])
        self.assertIn('name_legal_suffix_equivalent',r['evidence']['soft_signals'])
        self.assertEqual(r['identity'],'unresolved')
        self.assertEqual(r['route'],'RESIDUAL_SUSPICION')
        self.assertTrue(r['disposition']['report_recommended'])
        self.assertIn('SYN:KYB:CO-NAME',r['disposition']['source_refs'])
        self.assertIn('SYN:LN:CO-NAME',r['disposition']['source_refs'])

    def test_non_suffix_tokens_not_rewritten(self):
        self.assertIsNone(company_name_match_kind('MOCK ULTD', 'MOCK ULIMITED'))
        self.assertIsNone(company_name_match_kind('LTD', 'LIMITED'))
        self.assertIsNone(company_name_match_kind('MOCK LTD', 'MOCK INC'))
        self.assertEqual(normalize_company_name('MOCK CO., LTD'),normalize_company_name('MOCK COMPANY LIMITED'))

    def test_general_normalization_remains_unchanged(self):
        self.assertEqual(norm('MOCK CO., LTD.'),'mockcoltd')
        self.assertNotEqual(norm('MOCK CO., LTD.'),norm('MOCK CO., LIMITED'))

    def test_multilabel_case_gets_category_signal_gate_and_report(self):
        def mutate(d):
            d['hits'][0]['category']='Enforcement,Sanctions'
        r=run_case(mutate)
        self.assertEqual(r['identity'],'unresolved')
        self.assertIn('sanctions_category',r['suspicion']['factors'])
        self.assertTrue(r['gate']['requires_manual_screening_review'])
        self.assertTrue(r['disposition']['report_recommended'])
        self.assertIn('【执法/制裁】',r['disposition']['internal_note'])
        self.assertFalse(r['disposition']['manual_queue_required'])

    def test_multilabel_policy_trigger(self):
        def mutate(d):d['hits'][0]['category']='Enforcement,Sanctions'
        r=run_case(mutate,Policy(mandatory_compliance_categories=frozenset({'sanctions'})))
        self.assertTrue(r['gate']['compliance_escalation_required'])
        self.assertTrue(r['disposition']['compliance_escalation_required_by_policy'])

    def test_multilabel_no_source_no_report(self):
        def mutate(d):
            d['hits'][0]['category']='Enforcement,Sanctions'
            d['hits'][0]['risk_event'].clear()
        r=run_case(mutate)
        self.assertFalse(r['disposition']['report_recommended'])
        self.assertIsNone(r['suspicion']['score'])

    def test_labels_canonicalized_without_legal_regime_inference(self):
        self.assertEqual(risk_categories('Enforcement,Sanctions'),('enforcement','sanctions'))
        self.assertEqual(risk_categories('PEP; Adverse Media'),('pep','adverse_media'))
        self.assertEqual(risk_categories(''),('other',))

    def test_disabling_name_rule_removes_both_signals(self):
        def mutate(d):
            d['subjects'][0]['facts'][0]['value']='MOCK NOVA SEMICONDUCTOR CO., LIMITED'
            d['hits'][0]['facts'][0]['value']='MOCK NOVA SEMICONDUCTOR CO., LTD.'
        r=run_case(mutate,Policy(disabled_rules=frozenset({'P01_NAME'})))
        self.assertNotIn('name_exact',r['evidence']['soft_signals'])
        self.assertNotIn('name_legal_suffix_equivalent',r['evidence']['soft_signals'])
        self.assertFalse(r['disposition']['report_recommended'])

if __name__=='__main__':unittest.main()
