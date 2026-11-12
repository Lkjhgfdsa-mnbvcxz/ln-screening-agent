/* LN Local Workbench: the UI renders backend events. No model-generated UI steps. */
(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const app = { runId: null, eventSource: null, timer: null, snapshot: null,
    events: [], hitState: {}, selected: null, filter: 'all', refreshPending: false,
    started: null, capabilities: null };
  const title = {
    HIT_STARTED: '开始处理命中', SKILL_SELECTED: '加载 Skill 契约',
    POLICY_CHECK: 'PolicyGuard 校验', GATE_CHECK: '风险闸门检查',
    RULE_EVALUATED: '规则引擎判断', RULE_REGISTRY_CHECK: '规则注册表检查',
    TOOL_AUTHORIZED: '工具调用授权', TOOL_STARTED: '调查工具启动',
    TOOL_FINISHED: '调查工具完成', FACTS_RECEIVED: '新增事实候选',
    FACT_VERIFICATION: '事实核实结果', SUSPICION_EVALUATED: '疑似命中条件评估',
    HIT_FINISHED: '命中处理完成', HIT_RESULT_READY: '结论已就绪',
    CASE_STARTED: '工单开始', CASE_FINISHED: '工单完成',
    PRIOR_REVIEW_READ: '读取历史审核记录（仅展示）',
    PRIOR_COMPARISON: '历史结论与新判断对照', RUN_FAILED: '执行失败'
  };
  const stageNames = { orchestrator:'调度', skill:'Skill', policy:'Policy',
    risk_gate:'风险闸门', rule_engine:'规则引擎', investigation:'调查工具',
    disposition:'说明生成', suspicion:'内部风险计算', evidence:'证据',
    prior_review:'历史审核', other:'其他' };
  const statusNames = { completed:'已完成', running:'运行中', failed:'运行失败' };
  const fmt = (n) => typeof n === 'number' ? (n < 1 ? n.toFixed(3) : n.toFixed(1))+' ms' : '—';
  const node = (tag, cls, value) => {
    const el = document.createElement(tag);
    if(cls) el.className = cls;
    if(value !== undefined) el.textContent = String(value);
    return el;
  };
  const add = (parent, ...children) => { children.forEach(x => parent.appendChild(x)); return parent; };
  const noData = (target, value) => { target.replaceChildren(node('div','empty-message',value)); };
  const jsonBrief = (e) => {
    const d = e.details || {};
    const segments = [];
    for(const [k,v] of Object.entries(d)) {
      if(['decision','source_url','screening_url'].includes(k)) continue;
      const rendered = Array.isArray(v) ? v.join(', ') : typeof v === 'object' ? JSON.stringify(v) : String(v);
      if(rendered && rendered !== 'undefined') segments.push(k+': '+rendered.slice(0,135));
      if (segments.length >= 3) break;
    }
    return segments.join(' · ');
  };
  function scheduleRender() {
    if (app.refreshPending) return;
    app.refreshPending = true;
    requestAnimationFrame(() => { app.refreshPending = false; render(); });
  }
  function stateFor(id) { return app.hitState[id] || {phase:'排队中',state:'queued',duration:null}; }
  function recordEvent(event) {
    if(app.events.some(e => e.seq === event.seq)) return;
    app.events.push(event);
    app.events.sort((a,b)=>a.seq-b.seq);
    if(event.hit_id) {
      const h = app.hitState[event.hit_id] || {phase:'排队中',state:'queued',duration:null};
      if(event.kind === 'HIT_STARTED') { h.state='running'; h.phase='规则核验开始'; }
      else if (event.kind === 'HIT_FINISHED') { h.state='done'; h.phase='已完成'; h.duration=event.duration_ms; }
      else if (event.kind === 'TOOL_STARTED') h.phase='调查工具运行中';
      else if (event.kind === 'RULE_EVALUATED') h.phase='规则引擎已判断';
      else if (event.kind === 'FACT_VERIFICATION') h.phase='核实资料来源';
      else if (event.kind === 'SUSPICION_EVALUATED') h.phase='内部关联与风险判断已完成';
      app.hitState[event.hit_id] = h;
    }
    scheduleRender();
    if(['HIT_RESULT_READY','PRIOR_COMPARISON'].includes(event.kind)) loadSnapshot();
  }
  async function loadSnapshot() {
    if(!app.runId) return;
    try {
      const response = await fetch('/api/runs/'+app.runId, {cache:'no-store'});
      if(response.ok) { app.snapshot = await response.json(); scheduleRender(); }
    } catch(e) { $('runinfo').textContent='快照读取失败，请检查本地服务'; }
  }
  function renderHits() {
    const container=$('hits'); const snap=app.snapshot;
    if(!snap) return noData(container,'选择示例并开始运行。');
    const hitIds=snap.hit_ids || [];
    if(!app.selected || !hitIds.includes(app.selected)) app.selected=hitIds[0] || null;
    const frag=document.createDocumentFragment();
    for(const hitId of hitIds) {
      const h=stateFor(hitId); const decision=snap.decisions?.[hitId];
      const btn=node('button','hit'+(app.selected===hitId?' active':''));
      btn.type='button'; btn.onclick=()=>{app.selected=hitId; scheduleRender();};
      const left=node('div');
      const conclusion=decision?.disposition?.business_conclusion;
      const indicator=decision?.disposition?.final_indicator;
      add(left,node('strong','',hitId),node('small',conclusion?'business-text':'',conclusion || (decision?'尚未形成业务结论':h.phase)));
      if(indicator) add(left,node('small','indicator-text','最终指标：'+indicator));
      const right=node('div','hit-right');
      add(right,node('span','dot '+(h.state==='done'?'done':h.state==='running'?'running':'')),
        node('span','small-status',h.state==='done'?'已完成':h.state==='running'?'运行中':'等待中'));
      if(h.duration!==null) right.appendChild(node('small','timing',fmt(h.duration)));
      add(btn,left,right); frag.appendChild(btn);
    }
    container.replaceChildren(frag);
    container.classList.remove('empty');
  }
  function detailLine(parent, heading, value, clazz='') {
    const section=node('section','section '+clazz);
    add(section,node('h3','',heading),node('p','',value || '—')); parent.appendChild(section);
  }
  function renderDetail() {
    const container=$('detail'); const snap=app.snapshot;
    const decision=snap?.decisions?.[app.selected]; $('copy').disabled=!decision?.disposition?.internal_note; $('download').disabled=!snap?.report_ready;
    if(!app.selected) return noData(container,'点击左侧命中查看详情。');
    if(!decision) return noData(container,stateFor(app.selected).phase+' · 等待该命中完成');
    const disp=decision.disposition || {}; const root=node('div','detail-body');
    const outcome=disp.business_conclusion;
    const outcomePanel=node('section','business-result');
    const outcomeHeader=node('div','outcome-top');
    add(outcomeHeader,node('span','outcome-caption','业务结论（Agent 草稿）'),
      node('span','business-badge '+(outcome==='未命中'?'no-hit':outcome==='命中'?'hit-yes':outcome==='疑似命中'?'suspected':'none'),
        outcome || '—'));
    outcomePanel.appendChild(outcomeHeader);
    outcomePanel.appendChild(node('small','conclusion-hint',
      outcome ? '尚未经业务审批，不会自动写回 LN。' : '证据或处理条件不足，暂不生成结论；不能据此判为未命中。'));
    root.appendChild(outcomePanel);
    const indicator=disp.final_indicator;
    if(indicator) {
      const indPanel=node('section','final-indicator');
      const indHead=node('div','outcome-top');
      add(indHead,node('span','outcome-caption','最终指标（复核优先级 · 派生统计口径）'),
        node('span','business-badge '+(indicator==='命中'?'hit-yes':indicator==='疑似命中'?'suspected':'no-hit'),indicator));
      indPanel.appendChild(indHead);
      indPanel.appendChild(node('small','conclusion-hint',
        (disp.final_indicator_rule||'')+' · 仅用于统计与复核优先级；不改变业务结论，不自动放行或清除命中。'));
      const basis=disp.final_indicator_basis||[];
      if(basis.length) indPanel.appendChild(node('p','indicator-basis',basis.join('；')));
      root.appendChild(indPanel);
    }
    detailLine(root,'内部审核说明',disp.internal_note || '尚无说明','notice');
    if(disp.report_recommended) detailLine(root,'合规沟通草稿（尚未发送）',disp.compliance_message || '待生成','notice');
    const comparison=snap?.prior_comparisons?.[app.selected];
    if(comparison) {
      const priorLabels={true_hit:'命中',false_positive:'未命中',suspected_hit:'疑似命中'};
      const priorLabel=priorLabels[comparison.prior?.conclusion] || '未记录业务结论';
      const relationLabels={DIRECTIONALLY_CONSISTENT:'与本次建议方向一致',POTENTIAL_CONFLICT_REQUIRES_SOURCE_RECHECK:'与本次建议存在差异',NOT_COMPARABLE_OR_UNRESOLVED:'当前无法直接比较'};
      detailLine(root,'历史审核记录（独立保留，不作为本轮证据）',
        priorLabel+' · '+(relationLabels[comparison.comparison] || '待核对')+
        '\n记录：'+(comparison.prior?.recorded_at || '')+' · '+(comparison.prior?.source_ref || ''),'notice prior');
    }
    const matching=app.events.filter(x=>x.hit_id===app.selected);
    const technical=node('details','technical-details');
    technical.appendChild(node('summary','','查看证据来源与执行细节'));
    detailLine(technical,'身份判断 / 内部路由', (decision.identity || '—')+' · '+(decision.route || '—'));
    detailLine(technical,'触发规则与来源',
      '规则：'+(decision.rule_findings || []).map(x=>x.rule_id).slice(0,6).join('、')+
      '\n来源：'+(disp.source_refs || []).slice(0,8).join('、'));
    detailLine(technical,'底层判断依据',(decision.reasons || []).join('；') || '无');
    detailLine(technical,'技术处置状态',
      (disp.recommendation || '—')+' · 建议上报：'+(disp.report_recommended?'是':'否')+
      ' · 人工调查队列：'+(disp.manual_queue_required?'是':'否'));
    detailLine(technical,'实际执行记录',matching.map(x=> (title[x.kind]||x.kind)+
      (x.duration_ms!==undefined?' ('+fmt(x.duration_ms)+')':'' )).join(' → ') || '—');
    root.appendChild(technical);
    container.replaceChildren(root); container.classList.remove('empty');
  }
  function renderTimeline() {
    const container=$('timeline');
    let filtered=app.events.filter(e=>app.filter==='all' || e.stage===app.filter);
    if(app.selected) filtered=filtered.filter(e=>!e.hit_id || e.hit_id===app.selected);
    if(!filtered.length) return noData(container,'当前筛选没有事件。');
    const frag=document.createDocumentFragment();
    for(const event of filtered.slice(-160).reverse()) {
      const row=node('div','trace');
      const left=node('div','when',(event.elapsed_ms/1000).toFixed(2)+' s');
      const dot=node('div','trace-dot'); const body=node('div','trace-body');
      add(body,node('div','trace-label',(title[event.kind] || event.kind)+
          (event.hit_id?' · '+event.hit_id:'')),
        node('small','',jsonBrief(event)));
      row.append(left,dot,body);
      if(event.duration_ms!==undefined) row.appendChild(node('span','t',fmt(event.duration_ms)));
      frag.appendChild(row);
    }
    container.replaceChildren(frag); container.classList.remove('empty');
  }
  function renderPerf() {
    const container=$('perf'); const stats=app.snapshot?.performance || {};
    const records=Object.entries(stats).sort((a,b)=>b[1].duration_ms-a[1].duration_ms);
    if(!records.length) return noData(container,'已埋点的执行事件完成后，将显示真实测量耗时。');
    const max=Math.max(...records.map(x=>x[1].duration_ms),.001);
    const frag=document.createDocumentFragment();
    for(const [stage,v] of records.slice(0,10)) {
      const el=node('div','perf-row'); const head=node('div','head');
      add(head,node('span','',stageNames[stage] || stage),
        node('span','',fmt(v.duration_ms)+' · '+v.count+' 次'));
      const bar=node('div','bar'); const fill=node('div','fill');
      fill.style.width=Math.max(1,(v.duration_ms/max)*100)+'%';
      bar.appendChild(fill);add(el,head,bar);frag.appendChild(el);
    }
    container.replaceChildren(frag); container.classList.remove('empty');
  }
  function renderCapabilities() {
    const c=app.capabilities; if(!c) return;
    $('service').textContent='● 本地连接 · '+(c.has_real_llm?'模型可用':'模型未配置');
    const target=$('cap-list'); const frag=document.createDocumentFragment();
    for(const x of (c.skills || [])) {
      const el=node('div','cap-item');
      add(el,node('span','','Skill · '+x.slug),node('span','good','已注册'));frag.appendChild(el);
    }
    for(const [name,status] of Object.entries(c.tools || {})) {
      const connected=typeof status==='string' ? !/disabled|mock_only|not_connected|unavailable/i.test(status) : false;
      const el=node('div','cap-item');
      add(el,node('span','','Tool · '+name),node('span',connected?'good':'off',typeof status==='string'?status:JSON.stringify(status)));
      frag.appendChild(el);
    }
    target.replaceChildren(frag);
  }
  function render() {
    const snap=app.snapshot;
    $('total').textContent=snap?.hit_ids?.length ?? '—';
    $('complete').textContent=snap?.completed ?? '—';
    $('events-count').textContent=app.events.length;
    $('elapsed').textContent=snap ? fmt(snap.elapsed_ms) : '—';
    const status=snap?.status || '未开始';
    $('case-status').textContent=statusNames[status] || status;
    $('case-status').className='tag '+(status==='completed'?'done':status==='running'?'running':status==='failed'?'warn':'');
    $('runinfo').textContent = snap ? ('Run '+snap.run_id+' · '+snap.case_id) : '选择合成样例即可演示';
    renderHits();renderDetail();renderTimeline();renderPerf();
  }
  async function start() {
    $('run').disabled=true; $('run').textContent='正在启动…';
    if(app.eventSource) app.eventSource.close();
    if(app.timer) clearInterval(app.timer);
    app.events=[];app.hitState={};app.selected=null;app.snapshot=null;app.runId=null;
    render();
    try {
      const res=await fetch('/api/runs',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({case_key:$('case').value,workers:Number($('workers').value)})});
      const result=await res.json();
      if(!res.ok) throw new Error(result.error || '启动失败');
      app.runId=result.run_id;
      await loadSnapshot();
      const source=new EventSource('/api/runs/'+app.runId+'/events?after=0');
      app.eventSource=source;
      source.addEventListener('trace',e=>{
        try { recordEvent(JSON.parse(e.data)); } catch(err) { console.warn('event ignored',err); }
      });
      source.addEventListener('finished', async () => {
        source.close(); await loadSnapshot();
        $('live-label').textContent='✓ 本轮已结束';
        if(app.timer)clearInterval(app.timer);
      });
      source.onerror=()=>{
        $('live-label').textContent='连接中断 · 可刷新快照';
        loadSnapshot();
      };
      $('live-label').textContent='● SSE 事件流已连接';
      app.timer=setInterval(()=>{ if(app.snapshot?.status==='running') loadSnapshot(); },800);
    } catch(e) {
      $('runinfo').textContent='启动失败：'+e.message;
      $('live-label').textContent='未连接';
    } finally {
      $('run').disabled=false; $('run').textContent='▶ 开始运行';
    }
  }
  async function init() {
    try {
      const res=await fetch('/api/capabilities'); if(!res.ok)throw new Error('服务不可用');
      app.capabilities=await res.json();
      const select=$('case');
      for(const [id,label] of Object.entries(app.capabilities.cases||{})) {
        const opt=document.createElement('option'); opt.value=id; opt.textContent=label; select.appendChild(opt);
      }
      renderCapabilities();render();
    } catch(e) { $('service').textContent='● 服务连接失败'; }
  }
  $('run').addEventListener('click',start);
  $('download').addEventListener('click', async()=>{
    if(!app.runId || app.snapshot?.status!=='completed') return;
    const res=await fetch('/api/runs/'+app.runId+'/report');
    if(!res.ok) return;
    const payload=await res.blob();
    const url=URL.createObjectURL(payload);
    const link=document.createElement('a');
    link.href=url; link.download='LN_synthetic_'+app.runId+'_report.json';
    document.body.appendChild(link); link.click(); link.remove();
    URL.revokeObjectURL(url);
  });
  $('copy').addEventListener('click',async()=>{
    const note=app.snapshot?.decisions?.[app.selected]?.disposition?.internal_note || '';
    if(!note)return;
    try { await navigator.clipboard.writeText(note); $('copy').textContent='已复制'; }
    catch(e) { $('copy').textContent='复制失败'; }
    setTimeout(()=>$('copy').textContent='复制内部说明',1300);
  });
  for(const b of document.querySelectorAll('.filter')) b.addEventListener('click',()=>{
    app.filter=b.dataset.filter;
    document.querySelectorAll('.filter').forEach(x=>x.classList.toggle('on',x===b));
    renderTimeline();
  });
  init();
})();
