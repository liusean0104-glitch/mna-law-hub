const BASE = "https://law.moj.gov.tw/LawClass/";
const lawAllUrl  = c => `${BASE}LawAll.aspx?pcode=${c}`;
const artUrl     = (c,f) => `${BASE}LawSingle.aspx?pcode=${c}&flno=${encodeURIComponent(f)}`;
const cnSrch     = c => `${BASE}LawSearchCNKey.aspx?BTNType=CON&pcode=${c}`;

const DATA = window.__DATA__ || {LAWS:{}, PORTALS:[]};
const LAWS = DATA.LAWS;
const LAW_KEYS = Object.keys(LAWS);
const PORTALS = DATA.PORTALS;

const LS_FAV="mahub_favs_v3", LS_THEME="mahub_theme";
let favs = load(LS_FAV, []);
let view = {mode:"home", law:null, tab:"art", query:""};

function load(k,d){ try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } }
function save(k,v){ try { localStorage.setItem(k, JSON.stringify(v)); } catch {} }

(function(){ let t=localStorage.getItem(LS_THEME); if(!t) t=matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"; applyTheme(t); })();
function applyTheme(t){
  document.documentElement.setAttribute("data-theme",t);
  document.getElementById("themeIcon").textContent = t==="dark"?"☀️":"🌙";
  localStorage.setItem(LS_THEME,t);
}
document.getElementById("themeBtn").onclick = () =>
  applyTheme(document.documentElement.getAttribute("data-theme")==="dark"?"light":"dark");

const artPcode = (lawKey,a) => a.pcode || LAWS[lawKey].code;
const artLabel = (lawKey,a) => a.law || LAWS[lawKey].name;
const favId = (lawKey,a) => artPcode(lawKey,a)+"§"+a.no;
const isFav = id => favs.some(f=>f.id===id);
function toggleFav(item){
  const i = favs.findIndex(f=>f.id===item.id);
  if(i>=0) favs.splice(i,1); else favs.push(item);
  save(LS_FAV,favs); renderFavs(); renderMain();
}

function renderLawNav(){
  const el=document.getElementById("lawNav"); el.innerHTML="";
  LAW_KEYS.forEach(k=>{
    const L=LAWS[k];
    const b=document.createElement("button");
    b.className="nav-law"+(view.mode==="law"&&view.law===k?" active":"");
    b.style.setProperty("--accent",L.hue);
    b.innerHTML=`<span class="spine"></span><span class="nm">${L.name}</span><span class="code">${L.code}</span>`;
    b.onclick=()=>{ openLaw(k); closeDrawer(); };
    el.appendChild(b);
  });
}
function renderFavs(){
  const el=document.getElementById("favList"); el.innerHTML="";
  if(!favs.length){ el.innerHTML=`<div class="fav-empty">點任何條文或問答卡片右上角的 ★，收藏常查內容，會存在這台裝置。</div>`; return; }
  favs.forEach(f=>{
    const dest = f.url || artUrl(f.pcode,f.no);
    const label = f.no ? `<b style="font-family:Spectral,serif">§${f.no}</b> ${f.t||""}` : `${f.t||""}`;
    const mark = f.no ? "" : `<span class="fkind">Q</span>`;
    const row=document.createElement("div");
    row.className="fav-row"; row.style.setProperty("--accent", f.hue||"var(--gold)");
    row.title=`${f.no?"§"+f.no+"　":""}${f.t||""}`;
    row.innerHTML=`<span class="fspine"></span>${mark}
      <span class="ftitle">${label}</span>
      <button class="fx" aria-label="移除收藏">×</button>`;
    row.onclick=e=>{ if(e.target.classList.contains("fx")) return; window.open(dest,"_blank","noopener"); };
    row.querySelector(".fx").onclick=e=>{ e.stopPropagation(); toggleFav({id:f.id}); };
    el.appendChild(row);
  });
}
function renderPortals(){
  const el=document.getElementById("portalList"); el.innerHTML="";
  PORTALS.forEach(p=>{
    const a=document.createElement("a");
    a.className="portal"; a.href=p.url; a.target="_blank"; a.rel="noopener";
    a.innerHTML=`<span class="dot"></span><span>${p.name}</span><small>${p.note}</small><span class="ext">↗</span>`;
    el.appendChild(a);
  });
}

function articleCard(lawKey,a){
  const L=LAWS[lawKey], pc=artPcode(lawKey,a), id=favId(lawKey,a), on=isFav(id);
  const tags=(a.tags||[]).slice(0,3).map(t=>`<span>${t}</span>`).join("");
  const div=document.createElement("div");
  div.className="art"; div.style.setProperty("--accent",L.hue);
  div.innerHTML=`
    <div class="art-top">
      <span class="art-no">§${a.no}</span>
      <span class="art-lawtag">${artLabel(lawKey,a)}</span>
      <button class="art-star ${on?'on':''}" aria-label="收藏">${on?'★':'☆'}</button>
    </div>
    <div class="art-title">${a.t}</div>
    <div class="art-desc">${a.d}</div>
    <div class="art-foot">
      <a class="art-open" href="${artUrl(pc,a.no)}" target="_blank" rel="noopener">開啟條文 →</a>
      <div class="art-tags">${tags}</div>
    </div>`;
  div.querySelector(".art-star").onclick=()=>toggleFav({id, pcode:pc, no:a.no, t:a.t, hue:L.hue});
  return div;
}

function qaCard(lawKey,q){
  const L=LAWS[lawKey], id=q.url, on=isFav(id);
  const a=document.createElement("a");
  a.className="qa"; a.href=q.url; a.target="_blank"; a.rel="noopener";
  a.style.setProperty("--accent",L.hue);
  a.innerHTML=`
    <div class="qa-head">
      <span class="qa-kind">${q.k}</span>
      <span class="qa-src">${q.src}</span>
      <button class="qa-star ${on?'on':''}" aria-label="收藏">${on?'★':'☆'}</button>
    </div>
    <div class="qa-t">${q.t}</div>
    <div class="qa-d">${q.d}</div>`;
  a.querySelector(".qa-star").onclick=e=>{
    e.preventDefault(); e.stopPropagation();
    toggleFav({id, url:q.url, t:q.t, hue:L.hue});
  };
  return a;
}

function openHome(){ view={mode:"home",law:null,tab:"art",query:""}; document.getElementById("cmd").value=""; renderAll(); }
function openLaw(k,tab){ view={mode:"law",law:k,tab:tab||"art",query:""}; document.getElementById("cmd").value=""; renderAll(); window.scrollTo(0,0); }
function runSearch(q){ view={mode:"search",law:null,tab:"art",query:q}; renderAll(); window.scrollTo(0,0); }

function renderMain(){
  const m=document.getElementById("main"); m.innerHTML="";
  if(view.mode==="home") return renderHome(m);
  if(view.mode==="law") return renderLawView(m);
  if(view.mode==="search") return renderSearch(m);
}

function renderHome(m){
  const nArt=LAW_KEYS.reduce((s,k)=>s+LAWS[k].articles.length,0);
  const nQa =LAW_KEYS.reduce((s,k)=>s+LAWS[k].qa.length,0);
  m.insertAdjacentHTML("beforeend",`
    <div class="breadcrumb">首頁</div>
    <h1 class="page-h">併購・公司治理 法規查詢台</h1>
    <p class="page-sub">六部核心法規、${nArt} 條精選條文與 ${nQa} 個官方問答集／函釋入口，整合於一頁。
      上方指令列可直接輸入 <span class="fullcode">「證交 43-1」「公平 11」「投審 4」</span> 跳到該條原文，或輸入關鍵字全站搜尋。</p>`);

  const grid=document.createElement("div"); grid.className="law-grid";
  LAW_KEYS.forEach(k=>{
    const L=LAWS[k];
    const c=document.createElement("button");
    c.className="law-card"; c.style.setProperty("--accent",L.hue);
    c.innerHTML=`
      <div class="lc-name">${L.name}</div>
      <div class="lc-code">全國法規資料庫 · ${L.code}</div>
      <div class="lc-desc">${L.desc}</div>
      <div class="lc-count">條文 ${L.articles.length} ・ 問答函釋 ${L.qa.length} →</div>`;
    c.onclick=()=>openLaw(k);
    grid.appendChild(c);
  });
  m.appendChild(grid);

  m.insertAdjacentHTML("beforeend",`<div class="section-head"><h2>交易流程速取</h2><span class="count">從決議到主管機關關卡</span></div>`);
  const flow=[["company","185"],["ma","6"],["ma","12"],["sea","43-1"],["tender","14-1"],["ftc","11"],["ftc","12"],["invest","4"]];
  const g=document.createElement("div"); g.className="art-grid";
  flow.forEach(([k,no])=>{ const a=LAWS[k].articles.find(x=>x.no===no); if(a) g.appendChild(articleCard(k,a)); });
  m.appendChild(g);

  m.insertAdjacentHTML("beforeend",`<div class="section-head" style="margin-top:34px"><h2>官方問答集・函釋</h2><span class="count">各主管機關第一手見解</span></div>`);
  const qg=document.createElement("div"); qg.className="qa-list";
  [["ftc",0],["invest",0],["ma",0],["company",0],["sea",0],["tender",0]].forEach(([k,i])=>qg.appendChild(qaCard(k,LAWS[k].qa[i])));
  m.appendChild(qg);
}

function renderLawView(m){
  const k=view.law, L=LAWS[k];
  m.insertAdjacentHTML("beforeend",`
    <div class="breadcrumb">法規 · ${L.name}</div>
    <h1 class="page-h" style="color:${L.hue}">${L.name}</h1>
    <p class="page-sub">${L.desc}　<span class="fullcode">${L.full}（${L.code}）</span></p>
    <div class="tabs" style="--accent:${L.hue}">
      <button class="tab ${view.tab==="art"?"on":""}" data-tab="art">條文<span class="tn">${L.articles.length}</span></button>
      <button class="tab ${view.tab==="qa"?"on":""}" data-tab="qa">問答集・函釋<span class="tn">${L.qa.length}</span></button>
    </div>`);
  m.querySelectorAll(".tab").forEach(b=>b.onclick=()=>{ view.tab=b.dataset.tab; renderMain(); });

  if(view.tab==="art"){
    m.insertAdjacentHTML("beforeend",`
      <div class="section-head" style="--accent:${L.hue}">
        <h2>精選條文</h2><span class="count">${L.articles.length} 條</span>
        <a class="openall" href="${lawAllUrl(L.code)}" target="_blank" rel="noopener">開啟全文 ↗</a>
      </div>`);
    const g=document.createElement("div"); g.className="art-grid";
    L.articles.forEach(a=>g.appendChild(articleCard(k,a)));
    m.appendChild(g);

    const codes=[...new Set(L.articles.map(a=>artPcode(k,a)))];
    const links=codes.map(c=>{
      const nm=L.articles.find(a=>artPcode(k,a)===c);
      const label=nm.law||L.name;
      return `<a class="ftl" style="--accent:${L.hue}" href="${cnSrch(c)}" target="_blank" rel="noopener"><span class="sp"></span>${label} · 條文檢索 ↗</a>
              <a class="ftl" style="--accent:${L.hue}" href="${lawAllUrl(c)}" target="_blank" rel="noopener"><span class="sp"></span>${label} · 全文 ↗</a>`;
    }).join("");
    m.insertAdjacentHTML("beforeend",`
      <div class="fulltext" style="--accent:${L.hue}">
        找不到想要的條號？到官方資料庫做<b>全文檢索</b>，或開啟整部法規逐條瀏覽。
        <div class="ft-links">${links}</div>
      </div>`);
  } else {
    m.insertAdjacentHTML("beforeend",`
      <div class="section-head" style="--accent:${L.hue}">
        <h2>官方問答集與函釋</h2><span class="count">${L.qa.length} 個入口</span>
      </div>`);
    const g=document.createElement("div"); g.className="qa-list";
    L.qa.forEach(q=>g.appendChild(qaCard(k,q)));
    m.appendChild(g);
    m.insertAdjacentHTML("beforeend",`
      <div class="fulltext" style="--accent:${L.hue}">
        <b>提醒：</b>函釋與問答集是主管機關的行政見解，供實務操作參考，並非法院見解。個案爭議仍應回到法條文義、法院判決與專業意見判斷。
      </div>`);
  }
}

function renderSearch(m){
  const q=view.query.trim(), ql=q.toLowerCase();
  const artHits=[], qaHits=[];
  LAW_KEYS.forEach(k=>{
    LAWS[k].articles.forEach(a=>{
      const hay=(a.no+" "+a.t+" "+a.d+" "+(a.tags||[]).join(" ")+" "+artLabel(k,a)+" "+LAWS[k].name).toLowerCase();
      if(hay.includes(ql)) artHits.push([k,a]);
    });
    LAWS[k].qa.forEach(x=>{
      const hay=(x.t+" "+x.d+" "+x.k+" "+x.src+" "+LAWS[k].name).toLowerCase();
      if(hay.includes(ql)) qaHits.push([k,x]);
    });
  });
  m.insertAdjacentHTML("beforeend",`
    <div class="breadcrumb">搜尋結果</div>
    <h1 class="page-h">「${esc(q)}」</h1>
    <p class="page-sub">條文 ${artHits.length} 筆 ・ 問答函釋 ${qaHits.length} 筆。若要查全部條文，用下方官方全文檢索。</p>`);

  if(artHits.length){
    m.insertAdjacentHTML("beforeend",`<div class="section-head"><h2>條文</h2><span class="count">${artHits.length} 筆</span></div>`);
    const g=document.createElement("div"); g.className="art-grid";
    artHits.forEach(([k,a])=>g.appendChild(articleCard(k,a)));
    m.appendChild(g);
  }
  if(qaHits.length){
    m.insertAdjacentHTML("beforeend",`<div class="section-head" style="margin-top:30px"><h2>問答集・函釋</h2><span class="count">${qaHits.length} 筆</span></div>`);
    const g=document.createElement("div"); g.className="qa-list";
    qaHits.forEach(([k,x])=>g.appendChild(qaCard(k,x)));
    m.appendChild(g);
  }
  if(!artHits.length && !qaHits.length){
    m.insertAdjacentHTML("beforeend",`<div class="empty-state"><div class="big">⌕</div>精選內容中沒有符合的結果。<br>試試官方全文檢索，或用指令列直接跳條號。</div>`);
  }
  const links=LAW_KEYS.map(k=>{
    const L=LAWS[k];
    return `<a class="ftl" style="--accent:${L.hue}" href="${cnSrch(L.code)}" target="_blank" rel="noopener"><span class="sp"></span>${L.name} ↗</a>`;
  }).join("");
  m.insertAdjacentHTML("beforeend",`
    <div class="fulltext">
      到<b>全國法規資料庫全文檢索</b>查「${esc(q)}」（開啟對應法規的條文檢索頁後貼上關鍵字）：
      <div class="ft-links">${links}</div>
    </div>`);
}

function esc(s){ return s.replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function renderAll(){ renderLawNav(); renderFavs(); renderMain(); }

/* command bar */
const cmd=document.getElementById("cmd");
function parseCommand(raw){
  const s=raw.trim(); if(!s) return null;
  let lawKey=null, matched="";
  for(const k of LAW_KEYS) for(const al of LAWS[k].aliases){
    if(s.toLowerCase().includes(al.toLowerCase()) && al.length>matched.length){ lawKey=k; matched=al; }
  }
  const art=s.match(/(\d+(?:-\d+)?)/);
  if(lawKey && art){
    let sub=null;
    const SA=LAWS[lawKey].subAliases;
    if(SA){ let best=""; for(const a in SA) if(s.includes(a)&&a.length>best.length){ best=a; sub=SA[a]; } }
    return {type:"article", lawKey, flno:art[1], sub};
  }
  return {type:"search", query:s};
}
cmd.addEventListener("keydown",e=>{
  if(e.key!=="Enter") return;
  const p=parseCommand(cmd.value); if(!p) return;
  if(p.type==="article"){
    const L=LAWS[p.lawKey];
    let pc;
    if(p.sub) pc=p.sub;
    else { const hit=L.articles.find(a=>a.no===p.flno); pc=hit?artPcode(p.lawKey,hit):L.code; }
    window.open(artUrl(pc,p.flno),"_blank","noopener");
    view={mode:"law",law:p.lawKey,tab:"art",query:""}; renderAll();
    flashJump(L,pc,p.flno);
  } else runSearch(p.query);
});
let deb;
cmd.addEventListener("input",()=>{
  clearTimeout(deb);
  const v=cmd.value.trim();
  deb=setTimeout(()=>{
    if(!v){ if(view.mode==="search") openHome(); return; }
    const p=parseCommand(v);
    if(p&&p.type==="search") runSearch(v);
  },220);
});
function flashJump(L,pcode,flno){
  const m=document.getElementById("main");
  const b=document.createElement("div");
  b.className="fulltext"; b.style.setProperty("--accent",L.hue);
  b.style.margin="0 0 22px";
  const id=pcode+"§"+flno, on=isFav(id);
  b.innerHTML=`已在新分頁開啟 <b>§${flno}</b>（${pcode}）。
    <div class="ft-links">
      <a class="ftl" style="--accent:${L.hue}" href="${artUrl(pcode,flno)}" target="_blank" rel="noopener"><span class="sp"></span>再開一次 ↗</a>
      <a class="ftl" id="jumpFav" style="--accent:${L.hue}" href="#"><span class="sp"></span>${on?'已收藏 ★':'加入收藏 ☆'}</a>
    </div>`;
  m.insertBefore(b, m.children[3] || null);
  b.querySelector("#jumpFav").onclick=e=>{
    e.preventDefault();
    toggleFav({id, pcode, no:flno, t:"（手動收藏）", hue:L.hue});
  };
}

/* drawer */
const body=document.body;
function closeDrawer(){ body.classList.remove("nav-open"); }
document.getElementById("menuBtn").onclick=()=>body.classList.toggle("nav-open");
document.getElementById("backdrop").onclick=closeDrawer;
document.getElementById("homeBtn").onclick=()=>{ openHome(); closeDrawer(); };
document.getElementById("homeBtn").addEventListener("keydown",e=>{ if(e.key==="Enter"||e.key===" "){ e.preventDefault(); openHome(); }});
document.addEventListener("keydown",e=>{
  if(e.key==="/"&&document.activeElement!==cmd){ e.preventDefault(); cmd.focus(); }
  if(e.key==="Escape"){ closeDrawer(); if(document.activeElement===cmd) cmd.blur(); }
});

renderPortals(); renderAll();

/* expose helpers used by ai.js */
window.escapeHtml = esc;
window.openAiView = null;   // set by ai.js
