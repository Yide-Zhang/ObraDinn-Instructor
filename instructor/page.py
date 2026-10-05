"""提示页：本地 HTTP 服务 + 页面。

页面只拿到**已解锁**的节点，所以不会剧透。
「逐层」链的展开层数记在浏览器 localStorage，不占服务端状态。
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import re
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import render

DEFAULT_PORT = 8730
FONTS_DIR = Path(__file__).parent / "fonts"
FONT_TYPES = {".ttf": "font/ttf", ".otf": "font/otf",
              ".woff": "font/woff", ".woff2": "font/woff2"}
#: 窗口/任务栏图标（浏览器 `--app=` 窗口拿的是 favicon）。
#: exe 里它就在 instructor/ 旁边；开发期图标在仓库根。
ICON = Path(__file__).parent / "icon-instructor.png"
if not ICON.is_file():
    ICON = Path(__file__).parent.parent / "icon-instructor.png"

PAGE = r"""<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>《奥伯拉丁的回归》辅助程序</title>
<link rel="icon" type="image/png" href="icon-instructor.png">
<script>
/* 所有元素的尺寸 = 基准尺寸 x --s。
   --s 只由**窗口宽度**算出来，与窗口宽**成正比**（不看高度）。
   参考点：窗口 1200px 宽时正文 18px；比这宽就更大、窄就更小，同一比例线性推。
   夹在 14~32px，免得窗口极小时看不清、4K 上大得离谱。
   觉得字还小就调大 REF_FONT；觉得涨得太快就调大 REF_W。 */
(function () {
  var REF_W = 1200, REF_FONT = 18, MIN_FONT = 14, MAX_FONT = 32, CSS_BASE = 15;
  function fit() {
    var f = REF_FONT * (window.innerWidth / REF_W);          /* 想要的正文像素 */
    f = Math.max(MIN_FONT, Math.min(f, MAX_FONT));
    document.documentElement.style.setProperty("--s", (f / CSS_BASE).toFixed(4));
  }
  fit();
  window.addEventListener("resize", fit);
})();
</script>
<style>
/* 字体与「难度补丁」项目同款（IM FELL English Roman + 思源宋体），
   另加：粗体 = 思源宋体 Heavy，斜体中文 = 851 手写体，斜体拉丁 = Caveat。
   ⚠ 851 自带完整 ASCII，所以斜体栈里 Caveat 必须排在 851 前面。
   路径用相对写法，本地服务与静态导出两种情形都能用。 */
@font-face{font-family:"IMFe";src:url("fonts/IMFeENrm28P.ttf") format("truetype");
           font-weight:400;font-style:normal;font-display:swap}
@font-face{font-family:"SourceHanSerif";src:url("fonts/SourceHanSerifSC-SemiBold-subset.otf") format("opentype");
           font-weight:400;font-style:normal;font-display:swap}
@font-face{font-family:"SourceHanSerif";src:url("fonts/SourceHanSerifSC-Heavy-subset.otf") format("opentype");
           font-weight:700;font-style:normal;font-display:swap}
@font-face{font-family:"Hand851";src:url("fonts/851tegakizatsu-subset.otf") format("opentype");
           font-weight:400;font-style:normal;font-display:swap}
@font-face{font-family:"Caveat";src:url("fonts/Caveat-Regular.ttf") format("truetype");
           font-weight:400;font-style:normal;font-display:swap}
:root{--s:1;                      /* 缩放系数，由窗口大小算出来（见 head 里的脚本） */
      --bg:#333319;--fg:#e5ffff;
      --dim:rgba(229,255,255,.58);--line:rgba(229,255,255,.30);
      --soft:rgba(229,255,255,.14);--wash:rgba(229,255,255,.06);
      --font:"IMFe","SourceHanSerif","Songti SC","SimSun","Noto Serif CJK SC",Georgia,serif;
      /* 粗体：ascii 先走 IM FELL，汉字落到思源宋体 Heavy（它带 w700 那一档） */
      --font-bold:"IMFe","SourceHanSerif","Songti SC","SimSun","Noto Serif CJK SC",Georgia,serif;
      --font-hand:"Caveat","Hand851","IMFe","SourceHanSerif","Songti SC",cursive;
      --mono:ui-monospace,Consolas,"Courier New",monospace}
/* 全站无圆角、无滚动条（鼠标滚轮/触摸依旧能滚）；整页文字都不给人选中 */
*{box-sizing:border-box;border-radius:0;-webkit-user-select:none;user-select:none}
html,body{scrollbar-width:none;-ms-overflow-style:none}
html::-webkit-scrollbar,body::-webkit-scrollbar{width:0;height:0;display:none}
body{margin:0;background:var(--bg);color:var(--fg);font-size:15px;line-height:1.75;
     font-family:var(--font);zoom:var(--s)}
b,strong{font-family:var(--font-bold);font-weight:700}
i,em{font-family:var(--font-hand);font-style:normal}
.wrap{max-width:800px;margin:0 auto;padding:0 20px 80px}
header{position:relative;padding:30px 0 15px;border-bottom:1px solid var(--line);
       margin-bottom:24px}
h1{font-family:var(--font-bold);font-size:17px;font-weight:700;margin:0;letter-spacing:.12em}
/* 右上角：设置 / 操纵器 两个入口 + 浮层 */
.hdbtns{position:absolute;right:0;top:26px;display:flex;gap:8px}
.devbtn{font-family:var(--font);font-size:13px;
      color:var(--fg);background:transparent;border:1px solid var(--line);
      padding:5px 11px;cursor:pointer}
.devbtn:hover{background:var(--wash)}
.caret{display:inline-block;margin-left:7px;vertical-align:middle;
      border-left:4px solid transparent;border-right:4px solid transparent;
      border-top:5px solid var(--fg)}
.pop{position:absolute;right:0;top:100%;z-index:20;width:240px;margin-top:8px;
      background:var(--bg);border:1px solid var(--line);
      box-shadow:0 8px 26px rgba(0,0,0,.55);padding:13px}
.opt{display:block;width:100%;text-align:left;font-family:var(--font);font-size:14px;
      color:var(--fg);background:transparent;border:1px solid var(--line);
      padding:9px 12px;margin:0 0 7px;cursor:pointer}
.opt:last-child{margin-bottom:0}
.opt:hover{background:var(--wash)}
.opt[aria-pressed="true"]{border-color:var(--fg)}
.opt small{display:block;color:var(--dim);font-size:12px}
/* 设置面板（游戏目录 / 存档目录 / 书页钩子） */
.pop.wide{width:332px;max-height:min(78vh,560px);overflow:auto}
.row{display:flex;gap:8px;align-items:baseline;margin:0 0 7px}
.lb{color:var(--dim);font-size:12.5px;flex:none;width:60px}
.vl{flex:1;font-size:12.5px;word-break:break-all}
.vl.dim{color:var(--dim)}
.pi{width:100%;font-family:var(--font);font-size:12.5px;color:var(--fg);
      background:transparent;border:1px solid var(--line);padding:6px 8px;margin:0 0 7px}
/* 整页文字都不可选，但输入框里得能选（否则改了都没法复制） */
input.pi{-webkit-user-select:text;user-select:text}
.acts{display:flex;gap:6px;margin:0 0 11px}
.opt2{flex:1;font-family:var(--font);font-size:12.5px;color:var(--fg);
      background:transparent;border:1px solid var(--line);padding:6px 4px;cursor:pointer}
.opt2:hover{background:var(--wash)}
.sep{height:1px;background:var(--soft);margin:11px 0}
.msg{font-size:12px;color:var(--dim);margin:9px 0 0;white-space:pre-wrap}
.hidden{display:none}
/* 一个一级元素（`- 小节`）= 一块，标题可点，内容可折 */
.blk{border:1px solid var(--line);margin:0 0 12px}
.blk.isnew{border-color:var(--fg)}
.hd{display:flex;align-items:center;gap:9px;width:100%;text-align:left;cursor:pointer;
      font-family:var(--font-bold);font-size:15px;font-weight:700;color:var(--fg);
      background:transparent;border:0;border-bottom:1px solid var(--soft);
      padding:13px 17px}
.blk.col>.hd{border-bottom:0}
.hd:hover{background:var(--wash)}
.mk{font-family:var(--mono);font-size:13px;line-height:1;color:var(--dim);
      width:16px;flex:none}
.ttl{flex:0 1 auto}
.hd .mk:before{content:"\25BC"}          /* ▼ */
.blk.col>.hd .mk:before{content:"\25B6"} /* ▶ */
.newtag{font-family:var(--font);font-size:11px;font-weight:400;color:var(--bg);
      background:var(--fg);padding:0 7px;margin-left:4px;flex:none}
.bd{padding:14px 17px 16px}
.blk.col>.bd{display:none}
ul.items{list-style:none;margin:0;padding:0}
ul.items>li{margin:9px 0;padding-left:16px;position:relative}
ul.items>li:before{content:"";position:absolute;left:2px;top:.7em;width:4px;height:4px;
      background:var(--dim)}
ul.subs{list-style:none;margin:6px 0 0 4px;padding:0;opacity:.9}
ul.subs>li{margin:6px 0;padding-left:15px;position:relative}
ul.subs>li:before{content:"–";position:absolute;left:2px;color:var(--dim)}
/* 键位没有再包一层样式：`[Zoom]` 这些直接按正文排，只留一个裸 span 供 JS 换词 */
/* 逐层链：标题（「救救我！」）是**单独一块**，自己没有内容；点它才添下一块，
   添出来的「救救我！(X)」也是独立块（各带自己的标题栏、可折）。
   左边的记号不是三角：点它是「再加一块」；十层都出来之后标题块整个消失 */
.blk.chain>.hd .mk:before{content:"\FF0B"}
a{color:var(--fg);text-decoration:underline;text-underline-offset:3px}
footer{color:var(--dim);font-size:12.5px;padding-top:20px;border-top:1px solid var(--soft)}
.empty{color:var(--dim);padding:70px 0;text-align:center}
</style></head><body>
<div class="wrap">
<header>
  <h1>已解锁的提示</h1>
  <div class="hdbtns">
    <button class="devbtn" id="setbtn">设置<i class="caret"></i></button>
    <button class="devbtn" id="devbtn">操纵器：<span id="devname">键鼠</span><i class="caret"></i></button>
  </div>
  <div class="pop hidden" id="devpop">
    <button class="opt" data-dev="kbm">键鼠<small>键盘 / 鼠标</small></button>
    <button class="opt" data-dev="pad">手柄<small>Xbox · PlayStation 布局</small></button>
  </div>
  <div class="pop wide hidden" id="setpop">
    <div class="row"><span class="lb">游戏目录</span><span class="vl" id="v-game">—</span></div>
    <input class="pi" id="i-game" spellcheck="false" placeholder="手填游戏目录（含 ObraDinn_Data 的那一层）">
    <div class="acts">
      <button class="opt2" data-set="pick_game">选择…</button>
      <button class="opt2" data-set="auto_game">自动检测</button>
      <button class="opt2" data-set="apply_game">用上面路径</button>
    </div>
    <div class="sep"></div>
    <div class="row"><span class="lb">存档目录</span><span class="vl" id="v-saves">—</span></div>
    <input class="pi" id="i-saves" spellcheck="false" placeholder="留空 = 自动探测（一般不用改）">
    <div class="acts">
      <button class="opt2" data-set="pick_saves">选择…</button>
      <button class="opt2" data-set="default_saves">改回默认</button>
      <button class="opt2" data-set="apply_saves">用上面路径</button>
    </div>
    <div class="sep"></div>
    <div class="row"><span class="lb">书页钩子</span><span class="vl" id="v-hook">—</span></div>
    <div class="acts">
      <button class="opt2" data-set="hook_install">安装</button>
      <button class="opt2" data-set="hook_restore">还原</button>
      <button class="opt2" data-set="open_log">日志</button>
    </div>
    <p class="msg" id="setmsg"></p>
  </div>
</header>
<main id="main"></main>
<footer id="foot">正在追踪：—</footer>
</div>
<script>
const DATA = __PAYLOAD__;
const K_DEPTH = "obd.instr.depth.", K_COL = "obd.instr.col.",
      K_DEV = "obd.instr.device", K_ACK = "obd.instr.ack";

function ls(k, d){ const v = localStorage.getItem(k); return v === null ? d : v; }

// ---- 逐层链：已揭开几层 -------------------------------------------------
// 0 = 一层都没揭开（初始状态只有「救救我！」标题那一块）
function depth(nid){
  if (DATA.pre) return 1e9;                 // 预览模式：全展开
  const v = parseInt(ls(K_DEPTH + nid, "0"), 10);
  return isNaN(v) ? 0 : v;
}
function setDepth(nid, v){ localStorage.setItem(K_DEPTH + nid, String(v)); }

// ---- 页脚：正在追踪哪个档位 -------------------------------------------
// P1/P2/P3 -> 「第1/2/3个档位」；还没定位到存档就一个破折号。
function slotText(s){
  const m = /^P([123])$/.exec((s || "").toUpperCase());
  return m ? "第" + m[1] + "个档位" : "—";
}

// ---- 块的折叠 / 展开 ----------------------------------------------------
// 没手动设过折叠状态时：普通块默认展开，「新」块与**逐层链整块**默认折起
// （链是自取型内容：用户不需要就别把它摊在眼前）。玩家自己点过就记进
// localStorage，之后一直听手动的。
function colState(k, def){
  const v = localStorage.getItem(K_COL + k);
  return v === null ? def : v === "1";
}
function setCol(k, v){ localStorage.setItem(K_COL + k, v ? "1" : "0"); }

// ---- 「新」：解锁时刻晚于我上次确认过的那一刻 --------------------------
function ackMap(){ try { return JSON.parse(ls(K_ACK, "{}")) || {}; } catch (e){ return {}; } }
function isNew(b){ return b.t > 0 && b.t > (ackMap()[b.nid + ":" + b.idx] || 0); }
function markSeen(b){
  const a = ackMap();
  a[b.nid + ":" + b.idx] = b.t;
  localStorage.setItem(K_ACK, JSON.stringify(a));
}

// ---- 操纵器：决定正文里的键位文字 --------------------------------------
let DEV = ls(K_DEV, "");
function applyDev(){
  document.querySelectorAll("[data-kbm]").forEach(c => {
    c.textContent = (DEV === "pad") ? c.dataset.pad : c.dataset.kbm;
  });
  document.getElementById("devname").textContent = (DEV === "pad") ? "手柄" : "键鼠";
  document.querySelectorAll(".opt").forEach(o =>
    o.setAttribute("aria-pressed", String(o.dataset.dev === DEV)));
}

// ---- 设置面板：游戏目录 / 存档目录 / 书页钩子 ---------------------------
const setpop = document.getElementById("setpop"),
      setmsg = document.getElementById("setmsg"),
      setbtn = document.getElementById("setbtn");

function setRow(id, text, dim){
  const el = document.getElementById(id);
  el.textContent = text || "—";
  el.className = "vl" + (dim ? " dim" : "");
}

async function loadSet(clearMsg){
  if (clearMsg) setmsg.textContent = "";
  try {
    const s = await (await fetch("/api/settings")).json();
    const g = document.getElementById("v-game");
    if (s.game_dir){
      setRow("v-game", s.game_dir);
      g.title = s.game_saved ? "手动指定" : "自动检测到";
    } else {
      setRow("v-game", "没找到", true);
      g.title = s.game_why || "";
    }
    setRow("v-saves", s.saves_dir || s.saves_effective || "自动探测", !s.saves_dir);
    setRow("v-hook", s.hook || "—", !s.game_dir);
    document.getElementById("i-game").placeholder = s.game_saved
      ? "当前记住：" + s.game_saved : "手填游戏目录（含 ObraDinn_Data 的那一层）";
    document.getElementById("i-saves").placeholder = s.saves_dir
      ? "当前记住：" + s.saves_dir : "留空 = 自动探测（一般不用改）";
  } catch (e){
    setmsg.textContent = "读设置失败：" + e;
  }
}

async function setAct(act, path){
  setmsg.textContent = "…";
  try {
    const r = await fetch("/api/settings", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({act: act, path: path || ""})});
    const j = await r.json();
    setmsg.textContent = (j.ok ? "✔ " : "✘ ") + (j.message || "");
    await loadSet(false);
  } catch (e){
    setmsg.textContent = "✘ " + e;
  }
}

if (setbtn){
  setbtn.onclick = (e) => {
    e.stopPropagation();
    document.getElementById("devpop").classList.add("hidden");
    setpop.classList.toggle("hidden");
    if (!setpop.classList.contains("hidden")) loadSet(true);
  };
  setpop.querySelectorAll("[data-set]").forEach(b => {
    b.onclick = () => {
      const a = b.dataset.set;
      if (a === "apply_game") return setAct(a, document.getElementById("i-game").value.trim());
      if (a === "apply_saves") return setAct(a, document.getElementById("i-saves").value.trim());
      return setAct(a, "");
    };
  });
  document.addEventListener("click", (e) => {
    if (!setpop.contains(e.target) && !setbtn.contains(e.target))
      setpop.classList.add("hidden");
  });
}

function itemsHTML(b){
  let h = '<ul class="items">';
  b.items.forEach(it => {
    h += '<li>' + it.text;
    if (it.subs.length){
      h += '<ul class="subs">';
      it.subs.forEach(x => { h += '<li>' + x + '</li>'; });
      h += '</ul>';
    }
    h += '</li>';
  });
  return h + '</ul>';
}

function blockHTML(b){
  const k = b.nid + ":" + b.idx, nw = isNew(b), def = nw;
  return '<div class="blk' + (colState(k, def) ? ' col' : '') + (nw ? ' isnew' : '') +
         '" data-blk="' + k + '" data-def="' + (def ? 1 : 0) + '">' +
         '<button class="hd" data-k="' + k + '" data-def="' + (def ? 1 : 0) + '">' +
           '<span class="mk"></span><span class="ttl">' + b.title + '</span>' +
           (nw ? '<span class="newtag">新</span>' : '') +
         '</button><div class="bd">' + itemsHTML(b) + '</div></div>';
}

// ---- 逐层链 ------------------------------------------------------------
// 链上的小节（「救救我！(1)」「救救我！(2)」…）在数据里各自独立，但**初始都不显示**：
// 先只出一块只有标题的「救救我！」（点它就是「再添一块」），
// 每点一次多出一块「救救我！(X)」—— 它自己就是一块普通块（可折），
// 新的摆在标题底下（所以越往下越旧）。十层都出来之后标题块**整个消失**
// （全揭完了就没什么可点的了），只剩那十块。
function chainName(bs){
  const t = (bs[0] && bs[0].title) || "";
  return t.replace(/\s*[（(][^）)]*[）)]\s*$/, "").trim() || t;   // 「救救我！(1)」→「救救我！」
}
function chainHTML(bs, d){
  const nid = bs[0].nid;
  const shown = bs.filter(b => b.idx < d).sort((a, b) => b.idx - a.idx);   // 新的在上
  const next = bs.find(b => b.idx === d);
  let out = "";
  if (next){                                 // 还有没揭开的层才出标题块
    out += '<div class="blk chain' + (shown.length ? '' : ' col') + '" data-blk="' +
           nid + ':chain">' +
           '<button class="hd" data-chain="' + nid + '" data-next="' + next.idx + '">' +
             '<span class="mk"></span><span class="ttl">' + chainName(bs) + '</span>' +
           '</button></div>';
  }
  shown.forEach(b => {                       // 每个已揭开的层 = 一块独立的块
    const k = nid + ":" + b.idx;
    out += '<div class="blk' + (colState(k, false) ? ' col' : '') +
           '" data-blk="' + k + '">' +
           '<button class="hd" data-k="' + k + '" data-def="0">' +
             '<span class="mk"></span><span class="ttl">' + b.title + '</span>' +
           '</button><div class="bd">' + itemsHTML(b) + '</div></div>';
  });
  return out;
}

function render(){
  const main = document.getElementById("main");
  const out = [], dep = {}, byKey = {}, chains = {}, done = {};
  DATA.blocks.forEach(b => {
    if (b.chain) (chains[b.nid] = chains[b.nid] || []).push(b);
    else byKey[b.nid + ":" + b.idx] = b;          // 只有普通块能标「新」/确认
  });
  DATA.blocks.forEach(b => {
    if (!b.chain){ out.push(blockHTML(b)); return; }
    if (done[b.nid]) return;                       // 一条链只出一块
    done[b.nid] = true;
    if (dep[b.nid] === undefined) dep[b.nid] = depth(b.nid);
    out.push(chainHTML(chains[b.nid], dep[b.nid]));
  });
  main.innerHTML = out.length ? out.join("") :
    '<div class="empty">还没有解锁任何提示。<br>玩下去，进度一到就会出现在这里。</div>';

  main.querySelectorAll("button.hd").forEach(h => {
    const nid = h.dataset.chain;
    if (nid){                                   // 链的标题块：点一次添一块
      h.onclick = () => {
        const want = h.dataset.next;
        setDepth(nid, depth(nid) + 1);
        render();
        const el = main.querySelector('[data-blk="' + nid + ':' + want + '"]');
        if (el) el.scrollIntoView({behavior:"smooth", block:"center"});
      };
      return;
    }
    h.onclick = () => {                         // 普通块（含链上每一层）：折 / 展
      const k = h.dataset.k, def = h.dataset.def === "1";
      const wasCol = colState(k, def);
      setCol(k, !wasCol);
      const b = byKey[k];
      if (wasCol && b && isNew(b)) markSeen(b);   // 「展开一个新块」才算确认
      render();
    };
  });
  applyDev();                 // 重建了 DOM，按当前操纵器把键位文字重新填一遍
  document.getElementById("foot").textContent = "正在追踪：" + slotText(DATA.slot);
}

// ---- 操纵器浮层 --------------------------------------------------------
const pop = document.getElementById("devpop");
document.getElementById("devbtn").onclick = (e) => {
  e.stopPropagation();
  pop.classList.toggle("hidden");
};
pop.onclick = (e) => e.stopPropagation();
document.querySelectorAll(".opt").forEach(o => {
  o.onclick = () => {
    DEV = o.dataset.dev;
    localStorage.setItem(K_DEV, DEV);
    applyDev();
    pop.classList.add("hidden");
  };
});
document.addEventListener("click", () => pop.classList.add("hidden"));

render();
if (!DEV) pop.classList.remove("hidden");   // 本地还没有选择 -> 先让玩家选

// 静态导出（file://）时没有后端，别去轮询 /api/version（否则控制台一排 403）
if (location.protocol !== "file:") {
  let ver = DATA.version;
  setInterval(async () => {
    try {
      const r = await fetch("/api/version", {cache:"no-store"});
      const j = await r.json();
      if (j.version !== ver) location.reload();
    } catch (e) {}
  }, 3000);

  // 心跳：告诉后端「页面还活着」。
  // 关窗时用 sendBeacon 发个 bye —— 它是事件不是定时器，**不会被后台节流**，
  // 所以比靠定时器发心跳可靠得多。后端收到 bye 后会等几秒，
  // 期间没有新页面接手就退出（这个退出是用户关窗口时期望的行为）。
  const ping = () => fetch("/api/alive", {cache:"no-store"}).catch(() => {});
  ping();
  setInterval(ping, 5000);
  window.addEventListener("pagehide", () => {
    try { navigator.sendBeacon("/api/bye"); } catch (e) {}
  });
}
</script></body></html>
"""


def font_query() -> dict[str, str]:
    """字体文件名 -> 一个跟着文件走的版本号（mtime）。

    ⚠ 不加这个就会踩到「字体改了但页面上看不出来」：子集文件名不变，
    浏览器（HTTP 那条用 `max-age=86400`，file:// 那条也有磁盘缓存）会一直
    把**旧子集**喂给页面 —— 判断不了到底是没改对还是没重取。
    实测：同一文件用 `?v=<mtime>` 重取的能渲染 `挈`/`▼`，不带 `?v` 的还是旧的。
    """
    out: dict[str, str] = {}
    if FONTS_DIR.is_dir():
        for p in FONTS_DIR.iterdir():
            if p.is_file() and p.suffix.lower() in FONT_TYPES:
                out[p.name] = str(int(p.stat().st_mtime))
    return out


def page_html(payload: dict) -> str:
    """把 payload 与带版本号的字体 URL 填进模板（服务与静态导出共用）。"""
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    html = PAGE.replace("__PAYLOAD__", blob)
    for name, v in font_query().items():
        html = html.replace(f"fonts/{name}", f"fonts/{name}?v={v}")
    return html


def build_payload(nodes, unlocked, times: dict | None = None,
                  preview: bool = False, slot: str = "") -> dict:
    """只把已解锁的节点送进页面，摊平成「一级元素 = 块」并排好序。

    页面上不展示任何存档内容（书页数 / 已登记 / era …），只在页脚说一句
    「正在追踪：第 X 个档位」—— X 就是下面这个 slot。
    """
    return {"blocks": render.blocks(nodes, unlocked, times or {}),
            "pre": bool(preview),
            "slot": (slot or "").upper()}


class Site:
    """页面数据 + 本地服务。watcher 线程更新 payload，页面轮询 version。"""

    def __init__(self, port: int = DEFAULT_PORT):
        self.port = port
        self._lock = threading.Lock()
        self.payload: dict = {"version": 0, "blocks": [], "pre": False}
        self._httpd: ThreadingHTTPServer | None = None
        # 页面存活：`last_page` = 最后一次心跳；`bye_at` = 页面说「我关了」的时刻
        self.last_page = 0.0
        self.bye_at = 0.0

    def update(self, payload: dict) -> None:
        with self._lock:
            payload = dict(payload)
            payload["version"] = int(self.payload.get("version", 0)) + 1
            self.payload = payload

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self.payload)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    def serve_forever(self) -> None:
        site = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):                      # 静音
                pass

            def _send(self, code: int, body: bytes, ctype: str,
                      cache: str = "no-store") -> None:
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", cache)
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):                               # noqa: N802
                # ⚠ 路由只看路径：页面的字体 URL 挂着 `?v=<mtime>` 用来打破缓存，
                #   不切掉的话 `/fonts/x.otf?v=123` 后缀对不上白名单 -> 404 ->
                #   整个页面所有字体回落系统宋体。
                path = self.path.split("?", 1)[0]
                snap = site.snapshot()
                if path.startswith("/api/alive"):
                    site.last_page = time.time()
                    site.bye_at = 0.0
                    self._send(200, b"ok", "text/plain; charset=utf-8")
                    return
                if path.startswith("/fonts/"):
                    name = Path(path[len("/fonts/"):]).name
                    fp = FONTS_DIR / name
                    if fp.is_file() and fp.suffix.lower() in FONT_TYPES:
                        # 字体很大，给长缓存 —— 但页面里的 URL 挂着 mtime（见 font_query），
                        # 子集一重建 URL 就变，不靠这个 max-age 卡住。
                        self._send(200, fp.read_bytes(),
                                   FONT_TYPES[fp.suffix.lower()], "max-age=86400")
                    else:
                        self._send(404, b"no font", "text/plain; charset=utf-8")
                    return
                if path in ("/icon-instructor.png", "/favicon.ico"):
                    if ICON.is_file():
                        self._send(200, ICON.read_bytes(), "image/png", "max-age=86400")
                    else:
                        self._send(404, b"no icon", "text/plain; charset=utf-8")
                    return
                if path.startswith("/api/version"):
                    body = json.dumps({"version": snap["version"]}).encode()
                    self._send(200, body, "application/json; charset=utf-8")
                    return
                if path.startswith("/api/nodes"):
                    body = json.dumps(snap, ensure_ascii=False).encode()
                    self._send(200, body, "application/json; charset=utf-8")
                    return
                if path.startswith("/api/settings"):
                    body = json.dumps(settings_report(), ensure_ascii=False).encode()
                    self._send(200, body, "application/json; charset=utf-8")
                    return
                if path in ("/", "/index.html"):
                    html = page_html(snap).encode("utf-8")
                    self._send(200, html, "text/html; charset=utf-8")
                    return
                self._send(404, b"not found", "text/plain; charset=utf-8")

            def do_POST(self):                              # noqa: N802
                # 页面用到的两个 POST：关页面的心跳（/api/bye）、设置面板（/api/settings）
                path = self.path.split("?", 1)[0]
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n) if n else b""
                if path.startswith("/api/settings"):
                    if not _local_request(self):
                        self._send(403, b"forbidden", "text/plain; charset=utf-8")
                        return
                    try:
                        req = json.loads(body or b"{}")
                    except ValueError:
                        req = {}
                    res = apply_setting(req if isinstance(req, dict) else {})
                    self._send(200, json.dumps(res, ensure_ascii=False).encode(),
                               "application/json; charset=utf-8")
                    return
                if path.startswith("/api/bye"):
                    site.bye_at = time.time()
                    self._send(200, b"ok", "text/plain; charset=utf-8")
                    return
                self._send(404, b"not found", "text/plain; charset=utf-8")

        class Server(ThreadingHTTPServer):
            daemon_threads = True

        # 端口被占就往后顺延
        for p in range(self.port, self.port + 20):
            try:
                self._httpd = Server(("127.0.0.1", p), Handler)
                self.port = p
                break
            except OSError:
                continue
        if self._httpd is None:
            raise RuntimeError("没有可用端口")
        self._httpd.serve_forever()

    def start_thread(self) -> threading.Thread:
        t = threading.Thread(target=self.serve_forever, daemon=True,
                             name="instructor-http")
        t.start()
        # 等端口真正起来
        for _ in range(60):
            with socket.socket() as s:
                s.settimeout(0.1)
                if s.connect_ex(("127.0.0.1", self.port)) == 0:
                    break
            threading.Event().wait(0.05)
        return t


def ensure_fonts(quiet: bool = True) -> None:
    """字体子集不存在或已过期就重建（失败不影响其他功能，会回落系统衬线）。

    打包后的 exe 里没有源字体，`sources_present()` 会直接把我们挡掉。
    """
    try:
        from . import fonts as FT
        if not FT.sources_present():
            return
        if not FT.up_to_date():
            if not quiet:
                print("[i] 正在重建字体子集…")
            FT.build(quiet=quiet)
    except Exception as e:                                  # noqa: BLE001
        print(f"（字体子集重建失败：{type(e).__name__}: {e}）—— 回落到系统衬线字体")


def write_static(payload: dict, out: Path) -> Path:
    """把当前页面落成静态 html，并把字体一并拷到旁边的 fonts/ 里。

    路径是相对的（`fonts/...`），所以本地服务与 file:// 两种方式都能用。
    `--out` 给目录则写 index.html，给 .html 则写该文件。
    """
    import shutil

    out = Path(out)
    if out.suffix.lower() not in (".html", ".htm"):
        out = out / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    if FONTS_DIR.is_dir():
        fdir = out.parent / "fonts"
        fdir.mkdir(parents=True, exist_ok=True)
        for p in FONTS_DIR.iterdir():
            if p.is_file() and p.suffix.lower() in FONT_TYPES:
                shutil.copy2(p, fdir / p.name)
    if ICON.is_file():                      # favicon 也要跟着走
        shutil.copy2(ICON, out.parent / ICON.name)
    out.write_text(page_html(payload), encoding="utf-8")
    return out


# ----------------------------------------------------------------- 设置面板
# （页面右上角的「设置」——游戏目录 / 存档目录 / 书页钩子）
def _local_request(h) -> bool:
    """只让「本机 + 同源」的请求改设置。

    页面挂在 127.0.0.1 上，但浏览器里任何一个网页都能往这个端口发请求；
    而设置决定「要改哪个 DLL」—— 不能让别人瞎指一个路径。
    """
    host = (h.headers.get("Host") or "").split(":")[0].strip("[]")
    if host not in ("127.0.0.1", "localhost", "::1"):
        return False
    origin = h.headers.get("Origin") or ""
    if origin and not re.match(r"^https?://(127\.0\.0\.1|localhost|\[::1\])(:\d+)?$", origin):
        return False
    return True


def _capture(fn, *a, **kw) -> tuple[int, str]:
    """跑一个会 print 的函数，把输出捞回来（面板上要显示给用户看）。"""
    buf = io.StringIO()
    code = 1
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            code = int(fn(*a, **kw) or 0)
    except Exception as e:                               # noqa: BLE001
        buf.write(f"{type(e).__name__}: {e}")
    return code, buf.getvalue().strip()


def pick_folder(prompt: str) -> tuple[str, str]:
    """弹系统原生的「选择文件夹」。返回 (路径, 错误)；用户取消 = ("", "")。

    不用 tk：（HTTP 请求跑在工作线程里，tk 只能在主线程动）
    Windows 借 PowerShell 的 FolderBrowserDialog，macOS 用 osascript。
    提示语只能是 ASCII —— PowerShell 5.1 按 ANSI 读命令行，中文会乱。
    """
    import subprocess
    try:
        if sys.platform == "win32":
            ps = ("Add-Type -AssemblyName System.Windows.Forms;"
                  "$d = New-Object System.Windows.Forms.FolderBrowserDialog;"
                  f"$d.Description = '{prompt}';"
                  "$d.ShowNewFolderButton = $false;"
                  "if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK)"
                  " { [Console]::Out.Write($d.SelectedPath) }")
            r = subprocess.run(["powershell", "-NoProfile", "-STA", "-Command", ps],
                               capture_output=True, text=True,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        elif sys.platform == "darwin":
            r = subprocess.run(["osascript", "-e",
                                f'POSIX path of (choose folder with prompt "{prompt}")'],
                               capture_output=True, text=True)
        else:
            return "", "这个系统还没有文件夹选择器，请把路径手动填进输入框"
    except OSError as e:
        return "", f"打不开选择器：{e}"
    if r.returncode != 0:
        err = (r.stderr or "").strip()
        if "ancel" in err or "User canceled" in err:      # 取消不是错误
            return "", ""
        return "", err[:200] or "选择器返回了错误"
    return (r.stdout or "").strip(), ""


def open_path(p: Path) -> tuple[bool, str]:
    """用系统默认程序打开（日志、目录……）。"""
    import subprocess
    try:
        if sys.platform == "win32":
            os.startfile(str(p))                          # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(p)])           # noqa: S603
        else:
            subprocess.Popen(["xdg-open", str(p)])       # noqa: S603
    except OSError as e:
        return False, f"打不开：{e}"
    return True, f"已打开 {p}"


def settings_report() -> dict:
    """设置面板要的一览（游戏目录 / 存档目录 / 钩子状态 / 各种路径）。"""
    from . import facts as F, hook as HK, logfile as LOG, settings as SET
    d = HK.summary()
    d["saves_dir"] = SET.get("saves_dir")
    d["saves_effective"] = str(F.saves_dir() or "")
    d["settings_path"] = str(SET.path())
    d["log_path"] = str(LOG.path())
    return d


def apply_setting(req: dict) -> dict:
    """处理设置面板的一个动作；永远返回 {"ok": bool, "message": str}。"""
    from . import hook as HK, settings as SET
    act = str(req.get("act") or "")
    raw = str(req.get("path") or "").strip()

    if act in ("pick_game", "pick_saves"):
        got, err = pick_folder("Select the folder"
                               if act == "pick_game" else "Select the saves folder")
        if not got:
            return {"ok": False, "message": err or "已取消"}
        raw = got

    if act == "auto_game":
        p, why = HK.autodetect()
        return {"ok": p is not None,
                "message": f"自动找到并记住了：{p}" if p else why}

    if act in ("apply_game", "pick_game"):
        p, why = HK.set_game_dir(raw)
        return {"ok": p is not None, "message": f"已记住：{p}" if p else why}

    if act == "forget_game":
        HK.forget_game_dir()
        return {"ok": True, "message": "已忘掉记住的游戏目录"}

    if act == "default_saves":
        SET.update(saves_dir=None)
        return {"ok": True, "message": "已改回自动探测"}

    if act in ("apply_saves", "pick_saves"):
        d = Path(raw).expanduser()
        if not d.is_dir():
            return {"ok": False, "message": f"不是文件夹：{raw or '（空）'}"}
        SET.update(saves_dir=str(d))
        return {"ok": True, "message": f"已记住：{d}"}

    if act == "hook_install":
        code, txt = _capture(HK.install)
        return {"ok": code == 0, "message": txt or "（没有任何输出）"}
    if act == "hook_restore":
        code, txt = _capture(HK.restore)
        return {"ok": code == 0, "message": txt or "（没有任何输出）"}
    if act == "open_log":
        from . import logfile as LOG
        ok, msg = open_path(LOG.path())
        return {"ok": ok, "message": msg}
    return {"ok": False, "message": f"未知操作：{act}"}


# ----------------------------------------------------------------- 开 app 窗口
def _browser_exe() -> Path | None:
    """找一个 Chromium 系的浏览器（Edge / Chrome），用来开无地址栏的窗口。"""
    import os
    cands: list[Path] = []
    if sys.platform == "win32":
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        local = os.environ.get("LOCALAPPDATA", "")
        for base in (pf, pf86):
            for rel in (r"Microsoft\Edge\Application\msedge.exe",
                        r"Google\Chrome\Application\chrome.exe"):
                cands.append(Path(base) / rel)
        for rel in (r"Google\Chrome\Application\chrome.exe",
                    r"Microsoft\Edge\Application\msedge.exe"):
            if local:
                cands.append(Path(local) / rel)
    else:
        for p in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                  "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                  "/Applications/Chromium.app/Contents/MacOS/Chromium"):
            cands.append(Path(p))
    return next((c for c in cands if c.is_file()), None)


def open_app_window(url: str, profile_dir: Path | None = None) -> str:
    """用 Chromium 的 `--app` 开一个没有地址栏/标签栏的窗口；不行就退回默认浏览器。

    返回一句人话，说明到底用了什么（好写进日志）。
    `profile_dir` 给独立 profile —— 免得跟你平时的浏览器互相污染，也不会弹
    「恢复上次会话」这类东西。
    """
    import subprocess
    import webbrowser

    exe = _browser_exe()
    if exe is None:
        try:
            webbrowser.open(url)
            return "默认浏览器（没找到 Edge/Chrome，开的是普通标签页）"
        except Exception:                                    # noqa: BLE001
            return f"没打开，请手动访问 {url}"

    args = [str(exe), "--app=" + url, "--no-first-run",
            "--no-default-browser-check", "--window-size=1280,860"]
    if profile_dir is not None:
        try:
            profile_dir.mkdir(parents=True, exist_ok=True)
            args.append("--user-data-dir=" + str(profile_dir))
        except OSError:
            pass
    kwargs: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
                    "stdin": subprocess.DEVNULL}
    if sys.platform == "win32":
        kwargs["creationflags"] = 0x00000008        # DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    try:
        subprocess.Popen(args, **kwargs)
        return exe.name
    except OSError:
        try:
            webbrowser.open(url)
            return "默认浏览器"
        except Exception:                                    # noqa: BLE001
            return f"没打开，请手动访问 {url}"


def main() -> int:
    import time
    from . import hints as H
    nodes = H.load(Path(__file__).parent / "descriptions.txt")
    site = Site()
    site.update(build_payload(nodes, {n.nid for n in nodes}, preview=True))
    site.start_thread()
    print(f"页面: {site.url}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
