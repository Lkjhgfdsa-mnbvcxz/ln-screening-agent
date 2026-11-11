"""Generate fictional test data. Names and identifiers are invented; never real KYB PII."""
import json
from pathlib import Path
base=Path(__file__).parent/'examples'
base.mkdir(exist_ok=True)

def f(side, field, value, eid, origin=None, checked=True, context=""):
    return dict(side=side, field=field, value=value, evidence_id=eid,
                origin=origin or ("kyb_verified" if side=="applicant" else "ln_structured"),
                checked=checked, context=context)
P=[f('applicant','name','李文','kyb:p1:name'),
   f('applicant','dob','1995-06-15','kyb:p1:dob'),
   f('applicant','document_number','SYNTHETIC-P001','kyb:p1:id',context='CN_NATIONAL_ID'),
   f('applicant','region','北京市','kyb:p1:region'),
   f('applicant','business_region','北京市','kyb:p1:biz'),
   f('applicant','address','北京市朝阳区测试路8号','kyb:p1:address')]
C=[f('applicant','company_name','晨星贸易有限公司','kyb:c1:name'),
   f('applicant','registration_number','SYNTHETIC-COMPANY-001','kyb:c1:reg',context='COMPANY_REGISTRY'),
   f('applicant','address','北京市朝阳区测试路8号','kyb:c1:address')]
A=[f('applicant','address','北京市朝阳区测试路8号','kyb:a1:address')]
hits=[
    dict(hit_id='H01_DOB_CONFLICT',subject_id='p1',category='enforcement',facts=[f('hit','name','李文','ln:h1:name'),f('hit','dob','1988-03-05','ln:h1:dob')]),
    dict(hit_id='H02_TIME_IMPOSSIBLE',subject_id='p1',category='pep',facts=[f('hit','name','李文','ln:h2:name'),f('hit','acted_in_year','1990','official:h2:acted','official_primary',True,'held_position')]),
    dict(hit_id='H03_DOCUMENT_MATCH',subject_id='p1',category='sanctions',facts=[f('hit','name','李文','ln:h3:name'),f('hit','document_number','SYNTHETIC-P001','official:h3:doc','official_primary',True,'CN_NATIONAL_ID')]),
    dict(hit_id='H04_FORMER_PEP_UNRESOLVED',subject_id='p1',category='pep',facts=[f('hit','name','李文','ln:h4:name'),f('hit','region','北京市','ln:h4:region'),f('hit','pep_status','former','ln:h4:pep')]),
    dict(hit_id='H05_INVESTIGATE_THEN_EXCLUDE',subject_id='p1',category='enforcement',research_keys=['official:case5'],facts=[f('hit','name','李文','ln:h5:name')]),
    dict(hit_id='H06_SANCTIONS_NAME_ONLY',subject_id='p1',category='sanctions',facts=[f('hit','name','李文','ln:h6:name')]),
    dict(hit_id='H07_SUSPICIOUS_COINCIDENCE',subject_id='p1',category='adverse_media',facts=[f('hit','name','李文','ln:h7:name'),f('hit','address','北京市朝阳区测试路8号','ln:h7:address'),f('hit','region','北京市','ln:h7:region'),f('hit','event_recency','recent','ln:h7:recency')]),
    dict(hit_id='H08_PHOTO_DIFFERENCE',subject_id='p1',category='enforcement',facts=[f('hit','name','李文','ln:h8:name'),f('hit','photo_comparison','different','analyst:h8:photo','public_secondary',False)]),
    dict(hit_id='H09_COMPANY_REG_MATCH',subject_id='c1',category='sanctions',entity_type='company',facts=[f('hit','company_name','晨星贸易有限公司','ln:h9:name'),f('hit','registration_number','SYNTHETIC-COMPANY-001','official:h9:reg','official_primary',True,'COMPANY_REGISTRY')]),
    dict(hit_id='H10_ADDRESS_ONLY',subject_id='a1',category='sanctions',entity_type='address',facts=[f('hit','address','北京市朝阳区测试路8号','ln:h10:address')]),
    dict(hit_id='H11_DOB_MATCH_THEN_CONFLICT',subject_id='p1',category='enforcement',research_keys=['official:case11'],facts=[f('hit','name','李文','ln:h11:name'),f('hit','dob','1995-06-15','ln:h11:dob')]),
    dict(hit_id='H12_DOB_MATCH_ONLY',subject_id='p1',category='enforcement',facts=[f('hit','name','李文','ln:h12:name'),f('hit','dob','1995-06-15','ln:h12:dob')]),
]
for h in hits: h.setdefault('entity_type','person')
case={'case_id':'DEMO-2026-001','subjects':[
        {'subject_id':'p1','entity_type':'person','role':'董事/管理员','facts':P},
        {'subject_id':'c1','entity_type':'company','role':'入网商户','facts':C},
        {'subject_id':'a1','entity_type':'address','role':'商户地址','facts':A}],
      'hits':hits}
research={
    'official:case5':[f('hit','dob','1970-09-09','official:h5:dob','official_primary',True)],
    'official:case11':[f('hit','dob','1980-01-01','official:h11:dob','official_primary',True)],
}
(base/'demo_case.json').write_text(json.dumps(case,ensure_ascii=False,indent=2)+'\n', encoding='utf-8')
(base/'research_fixtures.json').write_text(json.dumps(research,ensure_ascii=False,indent=2)+'\n', encoding='utf-8')
