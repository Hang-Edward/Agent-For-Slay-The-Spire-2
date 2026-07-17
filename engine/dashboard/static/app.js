const state={snapshot:null,events:[],selectedRun:null,source:null};
const $=selector=>document.querySelector(selector);
const SCREEN_LABELS={MAIN_MENU:"主菜单",COMBAT:"战斗",MAP:"地图",EVENT:"事件",CARD_REWARD:"卡牌奖励",CARD_SELECT:"选择卡牌",CARD_SELECT_COMBAT:"战斗选牌",SPECIAL_EVENT:"特殊选择",SHOP:"商店",REST:"休息点",VICTORY:"战斗胜利",GAME_OVER:"对局结束"};
const PHASE_LABELS={waiting_for_game:"等待游戏",reading_state:"同步游戏状态",evaluating_candidates:"评估候选方案",waiting_for_deepseek:"DeepSeek 思考中",parsing_response:"解析模型回复",submitting_action:"发送动作",waiting_for_game:"等待游戏执行",state_advanced:"状态已更新",action_rejected:"动作被拒绝",error:"发生错误",run_started:"对局开始",run_completed:"对局结束"};
const INTENT_LABELS={ATTACK:"攻击",ATTACK_DEFEND:"攻击并防御",ATTACK_DEBUFF:"攻击并施加负面",DEFEND:"防御",DEFEND_BUFF:"防御并强化",BUFF:"强化",DEBUFF:"施加负面",ESCAPE:"逃跑",SLEEP:"休眠",STUN:"眩晕",UNKNOWN:"未知"};

function setText(node,value){if(node)node.textContent=value==null?"":String(value)}
function make(tag,className,text){const node=document.createElement(tag);if(className)node.className=className;if(text!=null)setText(node,text);return node}
function clear(node){node.replaceChildren();node.classList.remove("empty-state")}
function safeNumber(value,fallback=0){const number=Number(value);return Number.isFinite(number)?number:fallback}
function clamp(value,min,max){return Math.min(max,Math.max(min,value))}
function formatTime(value){if(!value)return "--:--:--";return new Date(value).toLocaleTimeString("zh-CN",{hour12:false})}
function screenLabel(value){return SCREEN_LABELS[value]||value||"等待游戏"}
function phaseLabel(value){return PHASE_LABELS[value]||value||"等待 Agent"}
async function fetchJson(path){const response=await fetch(path,{cache:"no-store"});if(!response.ok)throw new Error(`${response.status} ${response.statusText}`);return response.json()}

function appendStat(root,label,value,tone=""){
  const item=make("div",`stat ${tone}`.trim());
  item.append(make("span","stat-label",label),make("strong","stat-value",value));
  root.append(item);
}

function renderPlayer(game){
  const player=game.player||{};
  const root=$("#player-summary");clear(root);
  appendStat(root,"生命",`${safeNumber(player.current_hp)} / ${safeNumber(player.max_hp)}`,"health");
  appendStat(root,"格挡",safeNumber(player.block),"block");
  appendStat(root,"能量",`${safeNumber(player.energy)} / ${safeNumber(player.max_energy)}`,"energy");
  appendStat(root,"金币",safeNumber(player.gold),"gold");
}

function healthBar(current,max){
  const track=make("div","health-track");
  const fill=make("span","health-fill");
  fill.style.width=`${clamp(max?current/max*100:0,0,100)}%`;
  track.append(fill);return track;
}

function renderEnemies(game){
  const root=$("#enemy-list"),monsters=(game.monsters||[]).filter(monster=>!monster.is_gone);
  setText($("#enemy-count"),monsters.length?`${monsters.length} 名敌人`:"");clear(root);
  if(!monsters.length){root.classList.add("empty-state");setText(root,game.in_combat?"敌人已被击败":"尚未进入战斗");return}
  monsters.forEach(monster=>{
    const row=make("article","enemy-row");
    const top=make("div","row-top");
    top.append(make("strong","enemy-name",monster.name||monster.id||"敌人"),make("span","hp-text",`${safeNumber(monster.current_hp)} / ${safeNumber(monster.max_hp)}`));
    const intent=INTENT_LABELS[monster.intent]||monster.intent||"未知意图";
    const hits=Math.max(1,safeNumber(monster.intent_hits,1));
    const damage=safeNumber(monster.intent_damage);
    const intentText=damage>0?`${intent} ${damage}${hits>1?` × ${hits}`:""}`:intent;
    const bottom=make("div","enemy-meta");
    bottom.append(make("span","intent",intentText),make("span","block-text",safeNumber(monster.block)>0?`格挡 ${monster.block}`:""));
    row.append(top,healthBar(safeNumber(monster.current_hp),safeNumber(monster.max_hp)),bottom);root.append(row);
  });
}

function renderHand(game){
  const root=$("#hand-list"),hand=game.hand||[];setText($("#hand-count"),hand.length?`${hand.length} 张`:"");clear(root);
  if(!hand.length){root.classList.add("empty-state");setText(root,"暂无手牌");return}
  hand.forEach((card,index)=>{
    const row=make("div",`card-row ${card.is_playable===false?"disabled":""}`.trim());
    const cost=make("span","card-cost",safeNumber(card.cost_for_turn,card.cost));
    const body=make("div","card-body");
    const title=make("div","card-title");title.append(make("strong","",`${index+1}. ${card.name||card.id||"卡牌"}`),make("span","card-type",card.type||""));
    const facts=[];if(safeNumber(card.damage)>0)facts.push(`伤害 ${card.damage}`);if(safeNumber(card.block)>0)facts.push(`格挡 ${card.block}`);if(card.upgrades>0)facts.push(`+${card.upgrades}`);
    body.append(title,make("span","card-facts",facts.join(" · ")||(card.is_playable===false?card.playable_reason:"可使用")));
    row.append(cost,body);root.append(row);
  });
}

function optionName(game,index){const option=(game.options||[]).find(item=>safeNumber(item.index,-1)===safeNumber(index,-2));return option?.name||option?.id||`选项 ${safeNumber(index)+1}`}
function actionText(action,game){
  if(!action)return "等待新的决策";
  if(action.type==="play_card"){
    const card=(game.hand||[])[safeNumber(action.hand_index,-1)];
    const target=(game.monsters||[])[safeNumber(action.monster_index,0)];
    return target?`对 ${target.name||"敌人"} 打出 ${card?.name||`第 ${safeNumber(action.hand_index)+1} 张牌`}`:`打出 ${card?.name||`第 ${safeNumber(action.hand_index)+1} 张牌`}`;
  }
  if(action.type==="end_turn")return "结束当前回合";
  if(action.type==="use_potion")return `使用第 ${safeNumber(action.potion_slot)+1} 瓶药水`;
  if(action.type==="choose_option")return `选择：${optionName(game,action.option_index)}`;
  if(action.type==="choose_route")return `前往地图节点 ${action.row??"?"}:${action.column??"?"}`;
  return action.type||"等待新的决策";
}

function candidateText(candidate){
  const names=(candidate.names||[]).join(" → ")||candidate.name||candidate.action_key||"候选动作";
  const facts=[];if(safeNumber(candidate.damage)>0)facts.push(`${candidate.damage} 伤害`);if(safeNumber(candidate.block)>0)facts.push(`${candidate.block} 格挡`);if(candidate.estimated_hp_loss!=null)facts.push(`预计承伤 ${safeNumber(candidate.estimated_hp_loss)}`);
  return {names,facts:facts.join(" · ")||"等待效果评估",score:safeNumber(candidate.final_score,candidate.score).toFixed(1)};
}

function renderDecision(snapshot,game){
  const decision=snapshot.current_decision||{};
  setText($("#decision-source"),decision.source==="llm"?"DeepSeek":decision.source==="auto"?"自动规则":decision.source==="fallback"?"安全兜底":"待命");
  setText($("#decision-action"),actionText(decision.action,game));
  setText($("#decision-reason"),decision.explanation||"进入对局后，这里会显示 AI 的动作与取舍理由。");
  const metrics=$("#decision-metrics");clear(metrics);
  if(decision.elapsed_ms!=null)appendStat(metrics,"思考耗时",`${(safeNumber(decision.elapsed_ms)/1000).toFixed(1)} 秒`);
  if(decision.command)appendStat(metrics,"执行指令",decision.command,"command");
  const candidates=(decision.candidates||[]).slice().sort((a,b)=>safeNumber(b.final_score,b.score)-safeNumber(a.final_score,a.score)).slice(0,3);
  const root=$("#candidate-list");clear(root);
  if(!candidates.length){root.classList.add("empty-state");setText(root,"暂无候选方案");return}
  candidates.forEach((candidate,index)=>{
    const data=candidateText(candidate),row=make("div",`candidate ${index===0?"best":""}`.trim());
    row.append(make("span","candidate-rank",index===0?"推荐":`#${index+1}`));
    const body=make("div","candidate-body");body.append(make("strong","",data.names),make("span","",data.facts));
    row.append(body,make("strong","candidate-score",data.score));root.append(row);
  });
}

function eventSummary(event,game){
  const payload=event.payload||{},action=payload.action;
  const summaries={
    candidates_scored:["开始评估",`已生成 ${(payload.candidates||[]).length} 个候选方案`],
    llm_started:["DeepSeek 开始思考","正在比较收益、承伤与后续回合"],
    llm_finished:["DeepSeek 已回复",payload.elapsed_ms?`耗时 ${(safeNumber(payload.elapsed_ms)/1000).toFixed(1)} 秒`:"准备解析动作"],
    decision_parsed:["决策完成",actionText(action,game)],
    fallback_selected:["启用安全兜底",actionText(action,game)],
    action_sent:["正在执行",actionText(action,game)],
    action_accepted:["游戏已接收",actionText(action,game)],
    action_rejected:["游戏拒绝动作",actionText(action,game)],
    transition_observed:["游戏状态已推进",payload.reward?`本步奖励 ${safeNumber(payload.reward.total).toFixed(1)}`:"已观察到动作结果"],
    decision_error:["决策失败",payload.message||payload.error||"未知错误"],
    run_started:["新对局开始",payload.character||""],
    run_completed:["对局结束",payload.result==="victory"?"胜利":"失败"]
  };
  return summaries[event.event_type]||null;
}

function renderTimeline(game){
  const root=$("#event-stream");clear(root);
  const rows=state.events.map(event=>({event,summary:eventSummary(event,game)})).filter(item=>item.summary).slice(-30).reverse();
  if(!rows.length){root.classList.add("empty-state");setText(root,"等待 AI 开始思考");return}
  rows.forEach(({event,summary})=>{
    const tone=event.event_type.includes("error")||event.event_type.includes("rejected")?"error":event.event_type.includes("accepted")||event.event_type==="transition_observed"?"success":"";
    const row=make("article",`event ${tone}`.trim());
    row.append(make("time","event-time",formatTime(event.timestamp_utc)));
    const body=make("div","event-body");body.append(make("strong","",summary[0]),make("span","",summary[1]));row.append(body);root.append(row);
  });
}

function renderLive(){
  const snapshot=state.snapshot||{},game=snapshot.game_state||{};
  setText($("#connection-status"),phaseLabel(snapshot.phase));
  setText($("#run-summary"),game.act?`第 ${safeNumber(game.act)} 幕 · 第 ${safeNumber(game.floor)} 层 · 回合 ${safeNumber(game.turn)}`:screenLabel(game.screen_type));
  renderPlayer(game);renderEnemies(game);renderHand(game);renderDecision(snapshot,game);renderTimeline(game);
}

async function loadSnapshot(){state.snapshot=await fetchJson("/api/snapshot");const last=state.snapshot.last_event;if(last&&!state.events.some(event=>event.sequence===last.sequence))state.events.push(last);renderLive();updateStaleState()}
function connectEvents(){if(state.source)state.source.close();state.source=new EventSource("/api/events");state.source.onopen=()=>renderLive();state.source.addEventListener("telemetry",message=>{const event=JSON.parse(message.data);if(!state.events.some(item=>item.sequence===event.sequence))state.events=[...state.events,event].slice(-200);state.snapshot={...(state.snapshot||{}),last_event:event,phase:event.payload.phase||state.snapshot?.phase,state_revision:event.state_revision||state.snapshot?.state_revision,...(event.payload.snapshot_patch||{})};renderLive();updateStaleState()});state.source.onerror=()=>setText($("#connection-status"),"实时连接断开，正在重连")}

function renderHistory(data){
  const root=$("#history-list");clear(root);const runs=Array.isArray(data)?data:(data?.runs||[]);
  if(!runs.length){root.classList.add("empty-state");setText(root,"还没有保存的对局");return}
  runs.forEach(run=>{
    const row=make("button","history-row");row.type="button";
    const result=run.result==="victory"?"胜利":run.result==="loss"?"失败":"进行中";
    const body=make("div","history-body");body.append(make("strong","",run.character||run.class||"未知角色"),make("span","",`第 ${safeNumber(run.floor)} 层 · ${safeNumber(run.decision_count)} 次决策`));
    row.append(make("span",`result ${run.result||"active"}`,result),body,make("time","",run.updated_at?new Date(run.updated_at).toLocaleString("zh-CN"):""));
    row.addEventListener("click",()=>loadRun(run.run_id||run.id));root.append(row);
  });
}
async function loadRuns(){renderHistory(await fetchJson("/api/runs?offset=0&limit=50"))}
async function loadRun(id){state.selectedRun=await fetchJson(`/api/runs/${encodeURIComponent(id)}`);renderHistory([state.selectedRun?.manifest||state.selectedRun])}
function renderDebug(value){setText($("#debug-content"),JSON.stringify(value||state.snapshot||{},null,2))}
function updateStaleState(){const node=$("#connection-status"),timestamp=state.snapshot?.last_event?.timestamp_utc,stale=Boolean(timestamp)&&Date.now()-Date.parse(timestamp)>3000;node.classList.toggle("is-stale",stale);if(stale)setText(node,"状态超过 3 秒未更新")}

document.querySelectorAll("nav button").forEach(button=>button.addEventListener("click",()=>{
  document.querySelectorAll("nav button").forEach(item=>item.setAttribute("aria-selected",String(item===button)));
  const view=button.dataset.view;$("#live-view").hidden=view!=="live";$("#history-view").hidden=view!=="history";$("#debug-view").hidden=view!=="debug";
  if(view==="history")loadRuns().catch(error=>setText($("#history-list"),error));if(view==="debug")renderDebug();
}));
loadSnapshot().then(connectEvents).catch(error=>setText($("#connection-status"),`未连接：${error.message}`));setInterval(updateStaleState,1000);
