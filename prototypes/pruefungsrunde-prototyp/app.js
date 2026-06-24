const STORAGE_KEY = "pruefwerk-prototype-v1";

const seed = {
  candidates: [
    {id:1,firstName:"Lea",lastName:"Hoffmann",examNo:"FI-2026-1042",direction:"Anwendungsentwicklung",company:"Nordlicht Digital GmbH",attempt:1,mep:false},
    {id:2,firstName:"Jonas",lastName:"Weber",examNo:"FI-2026-1057",direction:"Systemintegration",company:"HanseNet Solutions AG",attempt:2,mep:true},
    {id:3,firstName:"Mara",lastName:"Schulz",examNo:"FI-2026-1081",direction:"Daten- und Prozessanalyse",company:"Datenspur Analytics GmbH",attempt:1,mep:false},
    {id:4,firstName:"Elias",lastName:"Koch",examNo:"FI-2026-1096",direction:"Digitale Vernetzung",company:"Elbwerke Technik KG",attempt:3,mep:false},
    {id:5,firstName:"Sofia",lastName:"Richter",examNo:"FI-2026-1113",direction:"Anwendungsentwicklung",company:"Pixelhafen Software GmbH",attempt:2,mep:false},
    {id:6,firstName:"Noah",lastName:"Bauer",examNo:"FI-2026-1128",direction:"Systemintegration",company:"Kernsysteme Nord GmbH",attempt:1,mep:true},
    {id:7,firstName:"Mila",lastName:"Wagner",examNo:"FI-2026-1144",direction:"Anwendungsentwicklung",company:"Cloudkontor AG",attempt:3,mep:true},
    {id:8,firstName:"Finn",lastName:"Krüger",examNo:"FI-2026-1162",direction:"Systemintegration",company:"Bytebrücke GmbH",attempt:1,mep:false},
    {id:9,firstName:"Amelie",lastName:"Wolf",examNo:"FI-2026-1179",direction:"Daten- und Prozessanalyse",company:"Prozessblick GmbH",attempt:2,mep:true},
    {id:10,firstName:"Paul",lastName:"Neumann",examNo:"FI-2026-1190",direction:"Digitale Vernetzung",company:"Netzraum Solutions KG",attempt:1,mep:false},
    {id:11,firstName:"Lina",lastName:"Schröder",examNo:"FI-2026-1205",direction:"Anwendungsentwicklung",company:"Codewerft GmbH",attempt:1,mep:false},
    {id:12,firstName:"Emil",lastName:"Hartmann",examNo:"FI-2026-1221",direction:"Systemintegration",company:"Infrapilot AG",attempt:2,mep:false}
  ],
  members: [
    {id:1,firstName:"Martin",lastName:"König",status:"Ordentliches Mitglied",function:"Vorsitzender",side:"Arbeitgeber",email:"martin.koenig@example.de",mobile:"+49 170 1234567",active:true,response:true},
    {id:2,firstName:"Dr. Anne",lastName:"Berg",status:"Ordentliches Mitglied",function:"Stellvertretender Vorsitzender",side:"Schule",email:"anne.berg@example.de",mobile:"+49 171 2345678",active:true,response:true},
    {id:3,firstName:"Tobias",lastName:"Rehm",status:"Ordentliches Mitglied",function:"Mitglied",side:"Arbeitnehmer",email:"tobias.rehm@example.de",mobile:"+49 172 3456789",active:true,response:true},
    {id:4,firstName:"Sabine",lastName:"Jahn",status:"Ordentliches Mitglied",function:"Mitglied",side:"Arbeitgeber",email:"sabine.jahn@example.de",mobile:"+49 173 4567890",active:true,response:true},
    {id:5,firstName:"Jan",lastName:"Peters",status:"Stellvertretendes Mitglied",function:"Mitglied",side:"Schule",email:"jan.peters@example.de",mobile:"+49 174 5678901",active:true,response:false},
    {id:6,firstName:"Nina",lastName:"Albrecht",status:"Stellvertretendes Mitglied",function:"Mitglied",side:"Arbeitnehmer",email:"nina.albrecht@example.de",mobile:"+49 175 6789012",active:true,response:true},
    {id:7,firstName:"Karim",lastName:"Özdemir",status:"Stellvertretendes Mitglied",function:"Mitglied",side:"Arbeitgeber",email:"karim.oezdemir@example.de",mobile:"+49 176 7890123",active:true,response:false},
    {id:8,firstName:"Claudia",lastName:"Mertens",status:"Stellvertretendes Mitglied",function:"Mitglied",side:"Schule",email:"claudia.mertens@example.de",mobile:"+49 177 8901234",active:true,response:true}
  ],
  locations: [
    {id:1,name:"Bildungszentrum HafenCity",street:"Am Sandtorkai 42",zip:"20457",city:"Hamburg",room:"Konferenzraum 3.12"},
    {id:2,name:"Berufliche Schule IT",street:"Eulenkamp 46",zip:"22049",city:"Hamburg",room:"Prüfungsraum B 204"}
  ],
  settings:{weekFrom:"2026-W47",weekTo:"2026-W49",examsPerDay:6,maxExamDaysPerWeek:3,lunch:true,locationId:1},
  candidateDates:[],availability:{},plan:[],planConfirmed:false,confirmedAt:null,planningModelVersion:2,candidateModelVersion:2
};

let state = loadState();
let toastTimer;

function clone(value){return JSON.parse(JSON.stringify(value));}
function loadState(){
  try {
    const saved=JSON.parse(localStorage.getItem(STORAGE_KEY) || "null")||{},requiresDayLimitMigration=Boolean(saved.settings&&!Object.prototype.hasOwnProperty.call(saved.settings,"maxExamDaysPerWeek")),requiresCandidateMigration=saved.candidateModelVersion!==2;
    const loaded={...clone(seed),...saved,settings:{...clone(seed.settings),...(saved.settings||{})}};delete loaded.settings.maxExamsPerWeek;
    if(requiresDayLimitMigration||saved.planningModelVersion!==2){loaded.plan=[];loaded.planConfirmed=false;loaded.confirmedAt=null;}
    loaded.planningModelVersion=2;
    loaded.candidates=loaded.candidates.map(candidate=>({...candidate,attempt:Math.max(1,Number(candidate.attempt)||1),mep:candidate.mep===true}));
    if(requiresCandidateMigration){
      const examples=new Map(seed.candidates.map(candidate=>[candidate.examNo,candidate]));
      loaded.candidates=loaded.candidates.map(candidate=>examples.has(candidate.examNo)?{...candidate,attempt:examples.get(candidate.examNo).attempt,mep:examples.get(candidate.examNo).mep}:candidate);
      loaded.plan=[];loaded.planConfirmed=false;loaded.confirmedAt=null;
    }
    loaded.candidateModelVersion=2;
    return loaded;
  }
  catch { return clone(seed); }
}
function saveState(){ localStorage.setItem(STORAGE_KEY,JSON.stringify(state)); }
function invalidatePlan(){state.plan=[];state.planConfirmed=false;state.confirmedAt=null;}
function totalRequiredExams(){return state.candidates.length+state.candidates.filter(candidate=>candidate.mep).length;}
function initials(item){return `${item.firstName?.trim()[0]||""}${item.lastName?.trim()[0]||""}`.toUpperCase();}
function fullName(item){return `${item.firstName} ${item.lastName}`;}
function escapeHtml(value=""){return String(value).replace(/[&<>'"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));}
function formatDate(date){return new Intl.DateTimeFormat("de-DE",{weekday:"short",day:"2-digit",month:"2-digit",year:"numeric"}).format(date);}
function shortDate(date){return new Intl.DateTimeFormat("de-DE",{weekday:"short",day:"2-digit",month:"2-digit"}).format(date);}
function showToast(message){
  const toast=document.querySelector("#toast"); toast.querySelector("p").textContent=message; toast.classList.add("show");
  clearTimeout(toastTimer);toastTimer=setTimeout(()=>toast.classList.remove("show"),3200);
}

const titles={dashboard:"Guten Morgen, Martin.",candidates:"Prüflinge",members:"Prüfungsausschuss",planning:"Terminplanung",locations:"Prüfungsorte"};
function showView(view){
  document.querySelectorAll(".view").forEach(el=>el.classList.toggle("active",el.id===`${view}-view`));
  document.querySelectorAll(".nav-item").forEach(el=>el.classList.toggle("active",el.dataset.view===view));
  document.querySelector("#page-title").textContent=titles[view];
  window.scrollTo({top:0,behavior:"smooth"});
}

function renderAll(){
  renderDashboard();renderCandidates();renderMembers();renderLocations();renderPlanningControls();renderAvailability();renderPlan();
}

function renderDashboard(){
  const active=state.members.filter(m=>m.active);const responses=active.filter(m=>m.response).length;
  const capacity=Number(state.settings.examsPerDay)||1;const days=minimumRequiredDays(totalRequiredExams(),capacity);
  document.querySelector("#candidate-nav-count").textContent=state.candidates.length;
  document.querySelector("#stat-candidates").textContent=state.candidates.length;
  document.querySelector("#stat-responses").textContent=`${responses} / ${active.length}`;
  document.querySelector("#stat-days").textContent=days;
  document.querySelector("#stat-members").textContent=active.length;
  document.querySelector("#hero-capacity").textContent=capacity;
  document.querySelector("#task-responses").textContent=responses===active.length?"Alle Rückmeldungen liegen vor":`${active.length-responses} Rückmeldungen stehen noch aus`;
  document.querySelector("#dashboard-member-list").innerHTML=active.slice(0,4).map(m=>`<div class="compact-member"><span class="avatar">${initials(m)}</span><span><strong>${escapeHtml(fullName(m))}</strong><small>${escapeHtml(m.side)} · ${escapeHtml(m.function)}</small></span><span class="response-badge ${m.response?"":"pending"}">${m.response?"Erledigt":"Offen"}</span></div>`).join("");
  const heroStatus=document.querySelector("#hero-status"),heroMessage=document.querySelector("#hero-message"),heroAction=document.querySelector("#hero-action");
  if(state.planConfirmed&&state.plan.length){
    heroStatus.className="status-pill confirmed";heroStatus.textContent="✓ Terminplanung abgeschlossen";
    heroMessage.innerHTML=`Der verbindliche Plan umfasst <strong>${state.plan.length} Prüfungstage</strong> mit ${state.plan.reduce((n,d)=>n+d.exams,0)} Prüfungen.`;
    heroAction.textContent="Terminplan öffnen →";document.querySelector("#round-progress").style.width="100%";document.querySelector("#round-status").textContent="Termine bestätigt";
  }else{
    heroStatus.className="status-pill amber";heroStatus.textContent="● Terminfindung läuft";
    heroMessage.innerHTML="Die Rückmeldefrist für die Verfügbarkeit endet in <strong>4 Tagen</strong>.";
    heroAction.textContent="Rückmeldungen ansehen →";document.querySelector("#round-progress").style.width="42%";document.querySelector("#round-status").textContent="Terminfindung läuft";
  }
  renderDashboardSchedule();
}

function renderDashboardSchedule(){
  const panel=document.querySelector("#dashboard-schedule"),grid=document.querySelector("#dashboard-schedule-grid");
  if(!state.planConfirmed||!state.plan.length){panel.classList.add("hidden");grid.innerHTML="";return;}
  const location=state.locations.find(l=>l.id===Number(state.settings.locationId));
  panel.classList.remove("hidden");
  grid.innerHTML=state.plan.map(day=>{
    const memberIds=[...new Set([...day.morning.crew,...(day.afternoon?.crew||[])])];
    const fallbackIds=[...new Set([day.morning.fallback,...(day.afternoon?[day.afternoon.fallback]:[])])];
    const lastSlot=slotTimes(day.exams,state.settings.lunch).filter(t=>!t.startsWith("Pause")).at(-1);
    const mepCount=day.mepCandidateIds?.length||0;
    return `<div class="dashboard-day"><div class="dashboard-date"><span>${new Intl.DateTimeFormat("de-DE",{month:"short"}).format(new Date(`${day.date}T12:00:00Z`))}</span><strong>${new Date(`${day.date}T12:00:00Z`).getUTCDate()}</strong></div><div class="dashboard-day-info"><strong>${formatDate(new Date(`${day.date}T12:00:00Z`))}</strong><small>${day.exams} Prüfungen${mepCount?` · davon ${mepCount} MEP`:""} · letzter Beginn ${lastSlot} Uhr</small><small>${escapeHtml(location?.name||"Kein Prüfungsort")} · ${escapeHtml(location?.room||"")}</small></div><div class="dashboard-crew"><span>${memberIds.map(id=>initials(getMember(id))).join(" · ")}</span><small>Fallback: ${fallbackIds.map(id=>fullName(getMember(id))).join(" / ")}</small></div></div>`;
  }).join("");
}

function renderCandidates(){
  const query=document.querySelector("#candidate-search")?.value.toLowerCase()||"";
  const direction=document.querySelector("#direction-filter")?.value||"";
  const filtered=state.candidates.filter(c=>(!direction||c.direction===direction)&&(!query||Object.values(c).join(" ").toLowerCase().includes(query)));
  document.querySelector("#candidate-table").innerHTML=filtered.length?filtered.map(c=>`<tr><td><strong>${escapeHtml(c.lastName)}, ${escapeHtml(c.firstName)}</strong><small>Winter 2026/27</small></td><td>${escapeHtml(c.examNo)}</td><td><span class="tag">${escapeHtml(c.direction)}</span></td><td><span class="tag attempt-${Math.min(c.attempt,3)}">${c.attempt}. Versuch</span></td><td><span class="tag ${c.mep?"mep":"none"}">${c.mep?"MEP":"Nein"}</span></td><td>${escapeHtml(c.company)}</td><td><button class="row-actions" data-delete-candidate="${c.id}" title="Datensatz löschen">×</button></td></tr>`).join(""):`<tr><td colspan="7" class="empty-state">Keine passenden Prüflinge gefunden.</td></tr>`;
  document.querySelector("#candidate-result-count").textContent=`${filtered.length} von ${state.candidates.length} Prüflingen`;
}

function renderMembers(){
  const active=state.members.filter(m=>m.active);
  const counts={Arbeitgeber:0,Arbeitnehmer:0,Schule:0};active.forEach(m=>counts[m.side]++);
  document.querySelector("#member-summary").innerHTML=`<div class="summary-chip"><small>Aktive Mitglieder</small><strong>${active.length}</strong></div>${Object.entries(counts).map(([key,val])=>`<div class="summary-chip"><small>${key}</small><strong>${val}</strong></div>`).join("")}`;
  document.querySelector("#member-grid").innerHTML=state.members.map(m=>`<article class="member-card"><div class="member-card-head"><span class="avatar">${initials(m)}</span><div><h3>${escapeHtml(fullName(m))}</h3><p>${escapeHtml(m.function)} · ${escapeHtml(m.status)}</p></div><span class="side-badge">${escapeHtml(m.side)}</span></div><div class="member-details"><span>✉ ${escapeHtml(m.email)} <b class="verified">✓ verifiziert</b></span><span>◇ ${escapeHtml(m.mobile||"Keine Mobilnummer")}</span></div></article>`).join("");
}

function renderLocations(){
  document.querySelector("#location-grid").innerHTML=state.locations.map(l=>`<article class="location-card"><div class="location-visual">⌖</div><div class="location-body"><h3>${escapeHtml(l.name)}</h3><p>${escapeHtml(l.street)}<br>${escapeHtml(l.zip)} ${escapeHtml(l.city)}</p><span class="location-room">${escapeHtml(l.room)}</span></div></article>`).join("");
  const select=document.querySelector("#plan-location");if(select){select.innerHTML=state.locations.map(l=>`<option value="${l.id}" ${Number(state.settings.locationId)===l.id?"selected":""}>${escapeHtml(l.name)} · ${escapeHtml(l.room)}</option>`).join("");}
}

function renderPlanningControls(){
  document.querySelector("#week-from").value=state.settings.weekFrom;
  document.querySelector("#week-to").value=state.settings.weekTo;
  document.querySelector("#exams-per-day").value=state.settings.examsPerDay;
  document.querySelector("#exam-days-per-week").value=state.settings.maxExamDaysPerWeek;
  document.querySelector("#lunch-toggle").checked=state.settings.lunch;
  const dayCapacity=Math.max(1,state.settings.examsPerDay),weeklyDays=Math.max(1,Math.min(5,state.settings.maxExamDaysPerWeek));
  const requiredExams=totalRequiredExams(),mepCount=state.candidates.filter(candidate=>candidate.mep).length;
  const days=minimumRequiredDays(requiredExams,dayCapacity);
  const weeks=planningWeekCount(),totalCapacity=weeks*weeklyDays*dayCapacity;
  document.querySelector("#capacity-days").textContent=days;
  document.querySelector("#capacity-candidates").textContent=requiredExams;
  document.querySelector("#capacity-total").textContent=totalCapacity;
  document.querySelector("#capacity-bar-fill").style.width=`${Math.min(100,(requiredExams/(totalCapacity||1))*100)}%`;
  const note=document.querySelector("#capacity-note");
  note.className=requiredExams>totalCapacity?"danger-text":"";
  note.textContent=requiredExams>totalCapacity?`Für ${state.candidates.length} Prüflinge und ${mepCount} zusätzliche MEPs werden ${requiredExams} Termine benötigt. Im Zeitraum fehlen ${requiredExams-totalCapacity} Plätze.`:`${state.candidates.length} reguläre Prüfungen${mepCount?` plus ${mepCount} MEP-Termine`:""}. MEPs werden immer an das Tagesende gesetzt.`;
}

function isoWeekStart(weekString){
  const [yearPart,weekPart]=weekString.split("-W");const year=Number(yearPart),week=Number(weekPart);
  const jan4=new Date(Date.UTC(year,0,4));const day=jan4.getUTCDay()||7;
  const monday=new Date(jan4);monday.setUTCDate(jan4.getUTCDate()-day+1+(week-1)*7);return monday;
}
function planningWeekCount(){
  const start=isoWeekStart(state.settings.weekFrom),end=isoWeekStart(state.settings.weekTo);
  return Math.max(0,Math.floor((end-start)/(7*24*60*60*1000))+1);
}
function minimumRequiredDays(candidateCount,perDay){return candidateCount?Math.ceil(candidateCount/Math.max(1,perDay)):0;}
function isoWeekKey(dateString){
  const date=new Date(`${dateString}T12:00:00Z`),day=date.getUTCDay()||7;date.setUTCDate(date.getUTCDate()+4-day);
  const year=date.getUTCFullYear(),yearStart=new Date(Date.UTC(year,0,1));const week=Math.ceil((((date-yearStart)/86400000)+1)/7);
  return `${year}-W${String(week).padStart(2,"0")}`;
}
function prepareCandidateDates(){
  syncSettings();const start=isoWeekStart(state.settings.weekFrom),end=isoWeekStart(state.settings.weekTo);end.setUTCDate(end.getUTCDate()+6);
  if(start>end){showToast("Die erste Kalenderwoche muss vor der letzten liegen.");return;}
  const dates=[];for(let d=new Date(start);d<=end;d.setUTCDate(d.getUTCDate()+1)){const weekday=d.getUTCDay();if(weekday>=1&&weekday<=5)dates.push(d.toISOString().slice(0,10));}
  state.candidateDates=dates;
  invalidatePlan();
  for(const member of state.members.filter(m=>m.active)){
    state.availability[member.id] ||= {};
    dates.forEach((date,index)=>{if(!state.availability[member.id][date]) state.availability[member.id][date]=defaultAvailability(member,index);});
  }
  saveState();renderAvailability();showToast(`${dates.length} mögliche Prüfungstage wurden berechnet.`);
}
function defaultAvailability(member,index){
  if(!member.response)return "pending";
  const pattern=(member.id*3+index)%11;if(pattern===0)return "no";if(pattern===4)return "am";if(pattern===7)return "pm";return "full";
}

const availabilityOptions=[["full","Ganztägig"],["am","Vormittags"],["pm","Nachmittags"],["no","Nicht verfügbar"],["pending","Offen"]];
function renderAvailability(){
  const wrap=document.querySelector("#availability-matrix");
  if(!state.candidateDates.length){wrap.innerHTML=`<div class="empty-state">Lege den Planungsrahmen fest und berechne anschließend die möglichen Tage.</div>`;return;}
  const dates=state.candidateDates.slice(0,10);
  wrap.innerHTML=`<table class="availability-table"><thead><tr><th>Mitglied</th>${dates.map(d=>`<th>${shortDate(new Date(`${d}T12:00:00Z`))}</th>`).join("")}</tr></thead><tbody>${state.members.filter(m=>m.active).map(m=>`<tr><td><div class="member-cell"><span class="avatar">${initials(m)}</span><span><strong>${escapeHtml(fullName(m))}</strong><small>${escapeHtml(m.side)}</small></span></div></td>${dates.map(d=>`<td><select data-availability-member="${m.id}" data-availability-date="${d}">${availabilityOptions.map(([value,label])=>`<option value="${value}" ${state.availability[m.id]?.[d]===value?"selected":""}>${label}</option>`).join("")}</select></td>`).join("")}</tr>`).join("")}</tbody></table>${state.candidateDates.length>10?`<div class="table-footer"><span>Die ersten 10 von ${state.candidateDates.length} möglichen Tagen werden angezeigt.</span><span>Der Planer berücksichtigt den gesamten Zeitraum.</span></div>`:""}`;
}

function availableFor(member,date,shift){const value=state.availability[member.id]?.[date];return value==="full"||value===shift;}
function chooseShiftCrew(date,shift,load){
  const members=state.members.filter(m=>m.active&&availableFor(m,date,shift));
  const crew=[];
  for(const side of ["Arbeitgeber","Arbeitnehmer","Schule"]){
    const options=members.filter(m=>m.side===side&&!crew.includes(m)).sort((a,b)=>(load[a.id]||0)-(load[b.id]||0)||a.id-b.id);
    if(!options.length)return null;crew.push(options[0]);
  }
  const fallback=members.filter(m=>!crew.includes(m)).sort((a,b)=>(load[a.id]||0)-(load[b.id]||0)||a.id-b.id)[0];
  if(!fallback)return null;return {crew,fallback};
}
function generatePlan(){
  syncSettings();if(!state.candidateDates.length)prepareCandidateDates();
  const load={},result=[],datesByWeek=new Map();
  let remaining=totalRequiredExams();
  state.candidateDates.forEach(date=>{const key=isoWeekKey(date);if(!datesByWeek.has(key))datesByWeek.set(key,[]);datesByWeek.get(key).push(date);});
  for(const dates of datesByWeek.values()){
    if(remaining<=0)break;
    let usedExamDays=0;
    const options=dates.map(date=>{
      const morning=chooseShiftCrew(date,"am",load);if(!morning)return null;
      const afternoon=chooseShiftCrew(date,"pm",load);
      const capacity=state.settings.examsPerDay>4&&!afternoon?Math.min(4,state.settings.examsPerDay):state.settings.examsPerDay;
      return {date,capacity};
    }).filter(Boolean).sort((a,b)=>b.capacity-a.capacity||a.date.localeCompare(b.date));
    for(const option of options){
      if(usedExamDays>=state.settings.maxExamDaysPerWeek||remaining<=0)break;
      const exams=Math.min(option.capacity,remaining),needsAfternoon=exams>4;
      const morning=chooseShiftCrew(option.date,"am",load),afternoon=needsAfternoon?chooseShiftCrew(option.date,"pm",load):null;
      if(!morning||(needsAfternoon&&!afternoon))continue;
      [...morning.crew,...(afternoon?.crew||[])].forEach(m=>load[m.id]=(load[m.id]||0)+1);
      load[morning.fallback.id]=(load[morning.fallback.id]||0)+.35;if(afternoon)load[afternoon.fallback.id]=(load[afternoon.fallback.id]||0)+.35;
      remaining-=exams;usedExamDays++;
      result.push({date:option.date,exams,morning:{crew:morning.crew.map(m=>m.id),fallback:morning.fallback.id},afternoon:afternoon?{crew:afternoon.crew.map(m=>m.id),fallback:afternoon.fallback.id}:null});
    }
  }
  result.sort((a,b)=>a.date.localeCompare(b.date));
  const plannedSlots=result.reduce((sum,day)=>sum+day.exams,0),mepCapacity=result.reduce((sum,day)=>sum+Math.max(0,day.exams-1),0),mepSlots=Math.min(state.candidates.filter(candidate=>candidate.mep).length,Math.max(0,plannedSlots-state.candidates.length),mepCapacity);
  const mepCandidateIds=state.candidates.filter(candidate=>candidate.mep).slice(0,mepSlots).map(candidate=>candidate.id);
  result.forEach(day=>day.mepCandidateIds=[]);
  for(let index=result.length-1;index>=0&&mepCandidateIds.length;index--){const day=result[index],count=Math.min(Math.max(0,day.exams-1),mepCandidateIds.length);day.mepCandidateIds=mepCandidateIds.splice(0,count);}
  state.plan=result;state.planConfirmed=false;state.confirmedAt=null;saveState();renderAll();
  if(remaining>0)showToast(`Für ${remaining} Prüfungstermine fehlt noch eine regelkonforme Besetzung.`);
  else if(mepSlots<state.candidates.filter(candidate=>candidate.mep).length)showToast("Planung erstellt · Nicht alle MEPs konnten ohne reinen MEP-Tag platziert werden.");
  else showToast("Planung erstellt · MEPs liegen jeweils am Tagesende.");
}
function getMember(id){return state.members.find(m=>m.id===id);}
function slotTimes(count,lunch){
  const times=[];let minutes=8*60+30;
  for(let i=0;i<count;i++){
    if(lunch&&minutes===12*60+30){times.push("Pause 12:30");minutes=13*60+30;}
    times.push(`${String(Math.floor(minutes/60)).padStart(2,"0")}:${String(minutes%60).padStart(2,"0")}`);minutes+=60;
  }
  return times;
}
function renderPlanSlots(day){
  const mepIds=day.mepCandidateIds||[],mepStart=day.exams-mepIds.length;let examIndex=0;
  return slotTimes(day.exams,state.settings.lunch).map(time=>{
    if(time.startsWith("Pause"))return `<span class="slot lunch">${time}</span>`;
    const isMep=examIndex>=mepStart,candidate=isMep?getCandidate(mepIds[examIndex-mepStart]):null;examIndex++;
    return `<span class="slot ${isMep?"mep-slot":""}">${time}${isMep?` · MEP ${escapeHtml(candidate?.lastName||"")}`:""}</span>`;
  }).join("");
}
function getCandidate(id){return state.candidates.find(candidate=>candidate.id===id);}
function renderCrew(shift){
  if(!shift)return `<span class="crew-chip">Keine Prüfungen geplant</span>`;
  return shift.crew.map(id=>{const m=getMember(id);return `<span class="crew-chip">${initials(m)} · ${escapeHtml(m.side)}</span>`;}).join("")+`<span class="crew-chip fallback">Fallback: ${escapeHtml(fullName(getMember(shift.fallback)))}</span>`;
}
function renderPlan(){
  const result=document.querySelector("#plan-result");if(!state.plan.length){result.classList.add("hidden");result.innerHTML="";return;}
  const location=state.locations.find(l=>l.id===Number(state.settings.locationId));
  const confirmed=Boolean(state.planConfirmed);
  result.classList.remove("hidden");result.innerHTML=`<div class="plan-header ${confirmed?"confirmed-plan-header":""}"><div><span class="eyebrow">${confirmed?"Verbindliche Planung":"Optimierter Vorschlag"}</span><h3>${state.plan.length} Prüfungstage · ${state.plan.reduce((n,d)=>n+d.exams,0)} Prüfungen</h3>${confirmed?`<p>Bestätigt am ${new Intl.DateTimeFormat("de-DE",{dateStyle:"medium",timeStyle:"short"}).format(new Date(state.confirmedAt))} · Kalendereinladungen sind vorgemerkt.</p>`:""}</div>${confirmed?`<div class="plan-header-actions"><span class="confirmed-badge">✓ Termine bestätigt</span><button class="button secondary" id="reopen-plan">Planung bearbeiten</button></div>`:`<button class="button primary" id="confirm-plan">Termine bestätigen</button>`}</div>${state.plan.map(day=>`<article class="plan-day ${confirmed?"confirmed-day":""}"><div class="plan-day-head"><div class="plan-date"><strong>${formatDate(new Date(`${day.date}T12:00:00Z`))}</strong><small>${escapeHtml(location?.name||"Kein Ort")}</small></div><div class="plan-slots">${renderPlanSlots(day)}</div><span class="valid-pill">✓ ${confirmed?"Bestätigt":"Regelkonform"}</span></div><div class="plan-crew"><div class="shift"><small>Vormittag · bis 12:30</small><div class="crew-list">${renderCrew(day.morning)}</div></div><div class="shift"><small>Nachmittag · ab 13:30</small><div class="crew-list">${renderCrew(day.afternoon)}</div></div></div></article>`).join("")}`;
  document.querySelector("#confirm-plan")?.addEventListener("click",()=>{state.planConfirmed=true;state.confirmedAt=new Date().toISOString();saveState();renderAll();showToast("Termine bestätigt · der Plan ist jetzt auf der Übersicht sichtbar.");});
  document.querySelector("#reopen-plan")?.addEventListener("click",()=>{state.planConfirmed=false;state.confirmedAt=null;saveState();renderAll();showToast("Die Planung ist wieder zur Bearbeitung geöffnet.");});
}

function syncSettings(){
  state.settings.weekFrom=document.querySelector("#week-from").value;
  state.settings.weekTo=document.querySelector("#week-to").value;
  state.settings.examsPerDay=Math.max(1,Number(document.querySelector("#exams-per-day").value)||1);
  state.settings.maxExamDaysPerWeek=Math.max(1,Math.min(5,Number(document.querySelector("#exam-days-per-week").value)||3));
  state.settings.lunch=document.querySelector("#lunch-toggle").checked;
  state.settings.locationId=Number(document.querySelector("#plan-location").value)||state.locations[0]?.id;
  saveState();renderDashboard();renderPlanningControls();
}

function parseCsv(text){
  const lines=text.replace(/^\uFEFF/,"").split(/\r?\n/).filter(Boolean);if(lines.length<2)return [];
  const delimiter=(lines[0].match(/;/g)||[]).length>=(lines[0].match(/,/g)||[]).length?";":",";
  const headers=lines[0].split(delimiter).map(h=>h.trim().toLowerCase());
  const names={vorname:"firstName",nachname:"lastName","name":"lastName","ihk-prüfungsnummer":"examNo","ihk-pruefungsnummer":"examNo",prüfungsnummer:"examNo",fachrichtung:"direction",ausbildungsbetrieb:"company",prüfungsversuch:"attempt",pruefungsversuch:"attempt",mep:"mep","mündliche ergänzungsprüfung":"mep","muendliche ergaenzungspruefung":"mep"};
  return lines.slice(1).map(line=>{const values=line.split(delimiter).map(v=>v.trim().replace(/^"|"$/g,""));const row={};headers.forEach((h,i)=>{if(names[h])row[names[h]]=values[i]||"";});row.attempt=Math.max(1,Number(row.attempt)||1);row.mep=/^(ja|j|true|1|x)$/i.test(row.mep||"");return row;}).filter(r=>r.firstName&&r.lastName&&r.examNo&&r.direction&&r.company);
}
function importCsv(file){
  const reader=new FileReader();reader.onload=()=>{
    const rows=parseCsv(reader.result),existing=new Set(state.candidates.map(c=>c.examNo.toLowerCase()));let added=0,duplicates=0;
    rows.forEach(row=>{if(existing.has(row.examNo.toLowerCase())){duplicates++;return;}existing.add(row.examNo.toLowerCase());state.candidates.push({...row,id:Date.now()+added});added++;});
    if(added)invalidatePlan();
    saveState();renderAll();showToast(`${added} Prüflinge importiert${duplicates?`, ${duplicates} Duplikate herausgefiltert`:""}.`);
  };reader.readAsText(file,"UTF-8");
}
function downloadTemplate(){
  const csv="Vorname;Nachname;IHK-Prüfungsnummer;Fachrichtung;Prüfungsversuch;MEP;Ausbildungsbetrieb\nErika;Muster;FI-2026-0001;Anwendungsentwicklung;1;Nein;Muster GmbH\n";
  const link=document.createElement("a");link.href=URL.createObjectURL(new Blob([csv],{type:"text/csv;charset=utf-8"}));link.download="prueflinge-importvorlage.csv";link.click();URL.revokeObjectURL(link.href);
}

document.addEventListener("click",event=>{
  const nav=event.target.closest("[data-view]");if(nav)showView(nav.dataset.view);
  const jump=event.target.closest("[data-view-jump]");if(jump)showView(jump.dataset.viewJump);
  const opener=event.target.closest("[data-open]");if(opener)document.querySelector(`#${opener.dataset.open}`).classList.add("open");
  if(event.target.classList.contains("modal-close")||event.target.classList.contains("modal-backdrop"))event.target.closest(".modal-backdrop")?.classList.remove("open");
  const remove=event.target.closest("[data-delete-candidate]");if(remove){state.candidates=state.candidates.filter(c=>c.id!==Number(remove.dataset.deleteCandidate));invalidatePlan();saveState();renderAll();showToast("Prüfling wurde aus dem Durchgang entfernt.");}
});
document.querySelector("#candidate-search").addEventListener("input",renderCandidates);
document.querySelector("#direction-filter").addEventListener("change",renderCandidates);
document.querySelector("#csv-input").addEventListener("change",e=>{if(e.target.files[0])importCsv(e.target.files[0]);e.target.value="";});
document.querySelector("#download-template").addEventListener("click",downloadTemplate);
document.querySelector("#prepare-dates").addEventListener("click",prepareCandidateDates);
document.querySelector("#generate-plan").addEventListener("click",generatePlan);
function updatePlanSetting(){syncSettings();invalidatePlan();saveState();renderAll();showToast("Die Planungsgrundlage wurde geändert. Bitte erstelle einen neuen Vorschlag.");}
document.querySelector("#exams-per-day").addEventListener("change",updatePlanSetting);
document.querySelector("#exam-days-per-week").addEventListener("change",updatePlanSetting);
document.querySelector("#lunch-toggle").addEventListener("change",updatePlanSetting);
document.querySelector("#plan-location").addEventListener("change",updatePlanSetting);
document.querySelector("#availability-matrix").addEventListener("change",e=>{
  if(!e.target.matches("[data-availability-member]"))return;const id=e.target.dataset.availabilityMember,date=e.target.dataset.availabilityDate;
  state.availability[id]||={};state.availability[id][date]=e.target.value;state.members.find(m=>m.id===Number(id)).response=true;invalidatePlan();saveState();renderDashboard();renderPlan();
});

document.querySelector("#candidate-form").addEventListener("submit",event=>{
  event.preventDefault();const data=Object.fromEntries(new FormData(event.currentTarget));
  if(state.candidates.some(c=>c.examNo.toLowerCase()===data.examNo.toLowerCase())){showToast("Diese IHK-Prüfungsnummer ist bereits vorhanden.");return;}
  state.candidates.push({...data,attempt:Math.max(1,Number(data.attempt)||1),mep:data.mep==="true",id:Date.now()});invalidatePlan();saveState();event.currentTarget.reset();event.currentTarget.querySelector('[name="attempt"]').value="1";event.currentTarget.closest(".modal-backdrop").classList.remove("open");renderAll();showToast("Prüfling wurde angelegt.");
});
document.querySelector("#member-form").addEventListener("submit",event=>{
  event.preventDefault();const data=Object.fromEntries(new FormData(event.currentTarget));state.members.push({...data,id:Date.now(),active:true,response:false});invalidatePlan();saveState();event.currentTarget.reset();event.currentTarget.closest(".modal-backdrop").classList.remove("open");renderAll();showToast("Mitglied wurde angelegt und kann nun seine E-Mail-Adresse verifizieren.");
});
document.querySelector("#location-form").addEventListener("submit",event=>{
  event.preventDefault();const data=Object.fromEntries(new FormData(event.currentTarget));state.locations.push({...data,id:Date.now()});saveState();event.currentTarget.reset();event.currentTarget.closest(".modal-backdrop").classList.remove("open");renderAll();showToast("Prüfungsort wurde angelegt.");
});
document.querySelector("#round-form").addEventListener("submit",event=>{event.preventDefault();event.currentTarget.closest(".modal-backdrop").classList.remove("open");showToast("Änderungen am Prüfungsdurchgang wurden gespeichert.");});

renderAll();
