"use strict";
var BpmnAsCode = (() => {
  var __defProp = Object.defineProperty;
  var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
  var __getOwnPropNames = Object.getOwnPropertyNames;
  var __hasOwnProp = Object.prototype.hasOwnProperty;
  var __export = (target, all) => {
    for (var name in all)
      __defProp(target, name, { get: all[name], enumerable: true });
  };
  var __copyProps = (to, from, except, desc) => {
    if (from && typeof from === "object" || typeof from === "function") {
      for (let key of __getOwnPropNames(from))
        if (!__hasOwnProp.call(to, key) && key !== except)
          __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
    }
    return to;
  };
  var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

  // src/browser.ts
  var browser_exports = {};
  __export(browser_exports, {
    DSL_PLACEHOLDER: () => DSL_PLACEHOLDER,
    ParseError: () => ParseError,
    ParseErrors: () => ParseErrors,
    compile: () => compile
  });

  // src/lexer.ts
  var KEYWORDS = /* @__PURE__ */ new Set([
    // existing
    "process",
    "start",
    "end",
    "task",
    "gateway",
    "subprocess",
    "by",
    "exclusive",
    "parallel",
    "inclusive",
    // new node types
    "catch",
    "throw",
    "boundary",
    "call",
    "pool",
    "lane",
    "note",
    "data",
    "datastore",
    // structural keywords
    "on",
    "in",
    // task types
    "user",
    "service",
    "script",
    "send",
    "receive",
    "manual",
    "businessrule",
    // event types
    "message",
    "timer",
    "signal",
    "error",
    "terminate",
    "escalation",
    "compensate",
    "conditional",
    "link",
    "none",
    // gateway type
    "eventbased",
    // modifiers
    "noninterrupting",
    "loop",
    "sequential"
  ]);
  function lex(source) {
    const tokens = [];
    let pos = 0;
    let line = 1;
    let col = 1;
    function peek(offset = 0) {
      return source[pos + offset];
    }
    function advance() {
      const ch = source[pos++];
      if (ch === "\n") {
        line++;
        col = 1;
      } else {
        col++;
      }
      return ch;
    }
    while (pos < source.length) {
      const startLine = line;
      const startCol = col;
      const ch = peek();
      if (ch === " " || ch === "	" || ch === "\r") {
        advance();
        continue;
      }
      if (ch === "\n") {
        advance();
        if (tokens.length > 0 && tokens[tokens.length - 1].type !== "NEWLINE") {
          tokens.push({ type: "NEWLINE", value: "\n", line: startLine, col: startCol });
        }
        continue;
      }
      if (ch === "#") {
        while (pos < source.length && peek() !== "\n") advance();
        continue;
      }
      if (ch === '"') {
        advance();
        let str = "";
        while (pos < source.length && peek() !== '"') str += advance();
        if (peek() === '"') advance();
        tokens.push({ type: "STRING", value: str, line: startLine, col: startCol });
        continue;
      }
      if (ch === "-" && peek(1) === "-" && peek(2) === "[") {
        advance();
        advance();
        advance();
        let condition = "";
        while (pos < source.length && peek() !== "]") condition += advance();
        if (peek() === "]") advance();
        if (peek() === "-") advance();
        if (peek() === "-") advance();
        if (peek() === ">") advance();
        tokens.push({ type: "COND_ARROW", value: condition, line: startLine, col: startCol });
        continue;
      }
      if (ch === "=" && peek(1) === "=" && peek(2) === ">") {
        advance();
        advance();
        advance();
        tokens.push({ type: "DEFAULT_ARROW", value: "==>", line: startLine, col: startCol });
        continue;
      }
      if (ch === "-" && peek(1) === ">") {
        advance();
        advance();
        tokens.push({ type: "ARROW", value: "->", line: startLine, col: startCol });
        continue;
      }
      if (ch === "~" && peek(1) === ">") {
        advance();
        advance();
        tokens.push({ type: "MSG_ARROW", value: "~>", line: startLine, col: startCol });
        continue;
      }
      if (ch === ":") {
        advance();
        tokens.push({ type: "COLON", value: ":", line: startLine, col: startCol });
        continue;
      }
      if (/[a-zA-Z_]/.test(ch)) {
        let ident = "";
        while (pos < source.length && /[a-zA-Z0-9_]/.test(peek())) ident += advance();
        const type = KEYWORDS.has(ident) ? "KEYWORD" : "IDENTIFIER";
        tokens.push({ type, value: ident, line: startLine, col: startCol });
        continue;
      }
      advance();
    }
    tokens.push({ type: "EOF", value: "", line, col });
    return tokens;
  }

  // src/validator.ts
  var START_EVENT_TYPES = /* @__PURE__ */ new Set([
    "none",
    "message",
    "timer",
    "signal",
    "conditional",
    "error"
  ]);
  var END_EVENT_TYPES = /* @__PURE__ */ new Set([
    "none",
    "message",
    "error",
    "terminate",
    "signal",
    "escalation",
    "compensate"
  ]);
  var CATCH_EVENT_TYPES = /* @__PURE__ */ new Set([
    "message",
    "timer",
    "signal",
    "conditional",
    "link",
    "escalation",
    "compensate"
  ]);
  var THROW_EVENT_TYPES = /* @__PURE__ */ new Set([
    "none",
    "message",
    "signal",
    "escalation",
    "compensate",
    "link"
  ]);
  var BOUNDARY_EVENT_TYPES = /* @__PURE__ */ new Set([
    "message",
    "timer",
    "signal",
    "error",
    "escalation",
    "compensate",
    "conditional"
  ]);
  function validate(process) {
    const errors = [];
    const laneIds = new Set(process.lanes.map((l) => l.id));
    const seen = /* @__PURE__ */ new Set();
    for (const node of process.nodes) {
      if (seen.has(node.id)) {
        errors.push({ message: `Duplicate node id: "${node.id}"`, nodeId: node.id });
      }
      seen.add(node.id);
    }
    const defaultSources = /* @__PURE__ */ new Set();
    for (const flow of process.flows) {
      if (flow.isDefault) {
        if (defaultSources.has(flow.source)) {
          errors.push({
            message: `Multiple default flows from node "${flow.source}"`,
            flowId: flow.id
          });
        }
        defaultSources.add(flow.source);
      }
    }
    for (const node of process.nodes) {
      if (node.type === "start" && node.eventType && !START_EVENT_TYPES.has(node.eventType)) {
        errors.push({
          message: `Start event "${node.id}" has invalid event type "${node.eventType}". Allowed: ${[...START_EVENT_TYPES].join(", ")}`,
          nodeId: node.id
        });
      }
      if (node.type === "end" && node.eventType && !END_EVENT_TYPES.has(node.eventType)) {
        errors.push({
          message: `End event "${node.id}" has invalid event type "${node.eventType}". Allowed: ${[...END_EVENT_TYPES].join(", ")}`,
          nodeId: node.id
        });
      }
      if (node.type === "catch" && node.eventType && !CATCH_EVENT_TYPES.has(node.eventType)) {
        errors.push({
          message: `Catch event "${node.id}" has invalid event type "${node.eventType}". Allowed: ${[...CATCH_EVENT_TYPES].join(", ")}`,
          nodeId: node.id
        });
      }
      if (node.type === "throw" && node.eventType && !THROW_EVENT_TYPES.has(node.eventType)) {
        errors.push({
          message: `Throw event "${node.id}" has invalid event type "${node.eventType}". Allowed: ${[...THROW_EVENT_TYPES].join(", ")}`,
          nodeId: node.id
        });
      }
      if (node.type === "boundary" && node.eventType && !BOUNDARY_EVENT_TYPES.has(node.eventType)) {
        errors.push({
          message: `Boundary event "${node.id}" has invalid event type "${node.eventType}". Allowed: ${[...BOUNDARY_EVENT_TYPES].join(", ")}`,
          nodeId: node.id
        });
      }
      if (node.laneId && !laneIds.has(node.laneId)) {
        errors.push({
          message: `Node "${node.id}" references unknown lane "${node.laneId}"`,
          nodeId: node.id
        });
      }
    }
    return errors;
  }

  // src/parser.ts
  var ParseError = class extends Error {
    constructor(message, line, col) {
      super(`Parse error at ${line}:${col} \u2014 ${message}`);
      this.line = line;
      this.col = col;
    }
    line;
    col;
  };
  var ParseErrors = class extends Error {
    constructor(errors) {
      super(errors.map((e) => e.message).join("\n"));
      this.errors = errors;
    }
    errors;
  };
  var NODE_KEYWORDS = /* @__PURE__ */ new Set([
    "start",
    "end",
    "task",
    "gateway",
    "subprocess",
    "catch",
    "throw",
    "boundary",
    "call",
    "note",
    "data",
    "datastore"
  ]);
  var TASK_TYPES = /* @__PURE__ */ new Set([
    "user",
    "service",
    "script",
    "send",
    "receive",
    "manual",
    "businessrule"
  ]);
  var EVENT_TYPES = /* @__PURE__ */ new Set([
    "none",
    "message",
    "timer",
    "signal",
    "error",
    "terminate",
    "escalation",
    "compensate",
    "conditional",
    "link"
  ]);
  var GATEWAY_TYPES = /* @__PURE__ */ new Set([
    "exclusive",
    "parallel",
    "inclusive",
    "eventbased"
  ]);
  var FLOW_TOKENS = /* @__PURE__ */ new Set([
    "ARROW",
    "COND_ARROW",
    "DEFAULT_ARROW",
    "MSG_ARROW"
  ]);
  function parse(source) {
    const tokens = lex(source);
    let pos = 0;
    function peek() {
      return tokens[pos];
    }
    function advance() {
      return tokens[pos++];
    }
    function expect(type, value) {
      const tok = peek();
      if (tok.type !== type || value !== void 0 && tok.value !== value) {
        throw new ParseError(
          `Expected ${type}${value ? ` "${value}"` : ""} but got ${tok.type} "${tok.value}"`,
          tok.line,
          tok.col
        );
      }
      return advance();
    }
    function expectId() {
      const tok = advance();
      if (tok.type !== "IDENTIFIER" && tok.type !== "KEYWORD") {
        throw new ParseError(
          `Expected identifier but got ${tok.type} "${tok.value}"`,
          tok.line,
          tok.col
        );
      }
      return tok;
    }
    function skipNewlines() {
      while (peek().type === "NEWLINE") advance();
    }
    function syncToNewline() {
      while (peek().type !== "NEWLINE" && peek().type !== "EOF") advance();
    }
    function isModifier() {
      const t = peek();
      return t.type !== "NEWLINE" && t.type !== "EOF" && !FLOW_TOKENS.has(t.type);
    }
    skipNewlines();
    expect("KEYWORD", "process");
    const processName = expect("STRING").value;
    const nodes = [];
    const flows = [];
    const pools = [];
    const lanes = [];
    const messageFlows = [];
    let flowCounter = 1;
    let msgFlowCounter = 1;
    const parseErrors = [];
    function makeFlowId() {
      return `Flow_${flowCounter++}`;
    }
    function makeMsgFlowId() {
      return `MsgFlow_${msgFlowCounter++}`;
    }
    skipNewlines();
    while (peek().type !== "EOF") {
      skipNewlines();
      const tok = peek();
      if (tok.type === "EOF") break;
      try {
        if (tok.type === "KEYWORD" && tok.value === "pool") {
          advance();
          expect("COLON");
          const id = expectId().value;
          const name = expect("STRING").value;
          pools.push({ id, name });
          continue;
        }
        if (tok.type === "KEYWORD" && tok.value === "lane") {
          advance();
          expect("COLON");
          const id = expectId().value;
          const name = expect("STRING").value;
          let pool = "";
          if (peek().type === "KEYWORD" && peek().value === "in") {
            advance();
            pool = expectId().value;
          }
          lanes.push({ id, name, pool });
          continue;
        }
        if (tok.type === "KEYWORD" && NODE_KEYWORDS.has(tok.value)) {
          advance();
          const rawType = tok.value;
          const nodeType = rawType === "note" ? "annotation" : rawType;
          expect("COLON");
          const id = expectId().value;
          const label = expect("STRING").value;
          const node = { id, type: nodeType, label };
          if (nodeType === "gateway") node.gatewayType = "exclusive";
          if (nodeType === "boundary") node.interrupting = true;
          while (isModifier()) {
            const mod = peek();
            const val = mod.value;
            if (mod.type === "KEYWORD" && val === "by") {
              advance();
              node.performer = expect("STRING").value;
              continue;
            }
            if (mod.type === "KEYWORD" && val === "on") {
              advance();
              const ref = expectId().value;
              if (nodeType === "boundary") node.attachedTo = ref;
              else if (nodeType === "annotation") node.annotationTarget = ref;
              continue;
            }
            if (mod.type === "KEYWORD" && val === "noninterrupting") {
              advance();
              node.interrupting = false;
              continue;
            }
            if (mod.type === "KEYWORD" && val === "loop") {
              advance();
              if (peek().type === "KEYWORD" && peek().value === "parallel") {
                advance();
                node.loopType = "parallel";
              } else if (peek().type === "KEYWORD" && peek().value === "sequential") {
                advance();
                node.loopType = "sequential";
              } else {
                node.loopType = "standard";
              }
              continue;
            }
            if ((mod.type === "KEYWORD" || mod.type === "IDENTIFIER") && GATEWAY_TYPES.has(val)) {
              advance();
              node.gatewayType = val;
              continue;
            }
            if ((mod.type === "KEYWORD" || mod.type === "IDENTIFIER") && TASK_TYPES.has(val)) {
              advance();
              node.taskType = val;
              continue;
            }
            if ((mod.type === "KEYWORD" || mod.type === "IDENTIFIER") && EVENT_TYPES.has(val)) {
              advance();
              node.eventType = val;
              continue;
            }
            if (mod.type === "KEYWORD" && val === "in") {
              advance();
              node.laneId = expectId().value;
              continue;
            }
            advance();
          }
          nodes.push(node);
          continue;
        }
        if (tok.type === "IDENTIFIER" || tok.type === "KEYWORD") {
          const firstTok = peek();
          if (pos + 1 < tokens.length) {
            const nextTok = tokens[pos + 1];
            if (!FLOW_TOKENS.has(nextTok.type)) {
              advance();
              continue;
            }
          }
          advance();
          let sourceId = firstTok.value;
          while (FLOW_TOKENS.has(peek().type)) {
            const arrowTok = advance();
            if (arrowTok.type === "MSG_ARROW") {
              const targetTok2 = expectId();
              let label;
              if (peek().type === "STRING") {
                label = advance().value;
              }
              messageFlows.push({
                id: makeMsgFlowId(),
                source: sourceId,
                target: targetTok2.value,
                label
              });
              sourceId = targetTok2.value;
              continue;
            }
            if (arrowTok.type === "DEFAULT_ARROW") {
              const targetTok2 = expectId();
              flows.push({
                id: makeFlowId(),
                source: sourceId,
                target: targetTok2.value,
                isDefault: true
              });
              sourceId = targetTok2.value;
              continue;
            }
            const condition = arrowTok.type === "COND_ARROW" ? arrowTok.value : void 0;
            const targetTok = expectId();
            flows.push({
              id: makeFlowId(),
              source: sourceId,
              target: targetTok.value,
              condition
            });
            sourceId = targetTok.value;
          }
          continue;
        }
        advance();
      } catch (e) {
        if (e instanceof ParseError) {
          parseErrors.push(e);
          syncToNewline();
        } else {
          throw e;
        }
      }
    }
    if (parseErrors.length > 0) {
      throw new ParseErrors(parseErrors);
    }
    const nodeIds = new Set(nodes.map((n) => n.id));
    function autoDeclareMissingNode(id) {
      if (!id) return;
      if (!nodeIds.has(id)) {
        const words = id.replace(/_/g, " ").replace(/([a-z])([A-Z])/g, "$1 $2").trim();
        const label = words.charAt(0).toUpperCase() + words.slice(1);
        nodes.push({
          id,
          type: "task",
          label: label || id
        });
        nodeIds.add(id);
      }
    }
    for (const flow of flows) {
      autoDeclareMissingNode(flow.source);
      autoDeclareMissingNode(flow.target);
    }
    for (const mf of messageFlows) {
      autoDeclareMissingNode(mf.source);
      autoDeclareMissingNode(mf.target);
    }
    for (const node of nodes) {
      if (node.type === "boundary" && node.attachedTo) {
        if (!nodeIds.has(node.attachedTo)) {
          throw new Error(`Boundary event "${node.id}" references unknown node: "${node.attachedTo}"`);
        }
      }
      if (node.type === "annotation" && node.annotationTarget) {
        if (!nodeIds.has(node.annotationTarget)) {
          throw new Error(`Annotation "${node.id}" references unknown node: "${node.annotationTarget}"`);
        }
      }
    }
    const process = { name: processName, nodes, flows, pools, lanes, messageFlows };
    const semanticErrors = validate(process);
    if (semanticErrors.length > 0) {
      throw new Error(semanticErrors.map((e) => e.message).join("\n"));
    }
    return process;
  }

  // src/layout.ts
  var SIZES = {
    start: { w: 36, h: 36 },
    end: { w: 36, h: 36 },
    task: { w: 120, h: 80 },
    gateway: { w: 50, h: 50 },
    subprocess: { w: 140, h: 80 },
    catch: { w: 36, h: 36 },
    throw: { w: 36, h: 36 },
    boundary: { w: 36, h: 36 },
    call: { w: 120, h: 80 },
    annotation: { w: 100, h: 40 },
    data: { w: 40, h: 50 },
    datastore: { w: 50, h: 50 }
  };
  var H_GAP = 95;
  var V_GAP = 75;
  var PADDING = 80;
  var POOL_HEADER = 30;
  var ATTACHED_TYPES = /* @__PURE__ */ new Set(["boundary", "annotation", "data", "datastore"]);
  function layout(process) {
    const { nodes, flows, pools, lanes, messageFlows } = process;
    const boundaryNodes = nodes.filter((n) => n.type === "boundary");
    const annotationNodes = nodes.filter((n) => n.type === "annotation");
    const dataNodes = nodes.filter((n) => n.type === "data" || n.type === "datastore");
    const flowNodes = nodes.filter((n) => !ATTACHED_TYPES.has(n.type));
    const nodeMap = new Map(nodes.map((n) => [n.id, n]));
    const flowNodeIds = new Set(flowNodes.map((n) => n.id));
    const outgoing = new Map(flowNodes.map((n) => [n.id, []]));
    const incoming = new Map(flowNodes.map((n) => [n.id, []]));
    for (const f of flows) {
      if (!flowNodeIds.has(f.source) || !flowNodeIds.has(f.target)) continue;
      outgoing.get(f.source).push(f.target);
      incoming.get(f.target).push(f.source);
    }
    const visited = /* @__PURE__ */ new Set();
    const visiting = /* @__PURE__ */ new Set();
    const backEdges = /* @__PURE__ */ new Set();
    function dfs(id) {
      if (visited.has(id)) return;
      visiting.add(id);
      for (const next of outgoing.get(id) ?? []) {
        if (visiting.has(next)) backEdges.add(`${id}->${next}`);
        else dfs(next);
      }
      visiting.delete(id);
      visited.add(id);
    }
    for (const n of flowNodes) dfs(n.id);
    const fwdOut = new Map(flowNodes.map((n) => [n.id, []]));
    const fwdIn = new Map(flowNodes.map((n) => [n.id, []]));
    for (const f of flows) {
      if (!flowNodeIds.has(f.source) || !flowNodeIds.has(f.target)) continue;
      if (backEdges.has(`${f.source}->${f.target}`)) continue;
      fwdOut.get(f.source).push(f.target);
      fwdIn.get(f.target).push(f.source);
    }
    const level = /* @__PURE__ */ new Map();
    const queue = [];
    for (const n of flowNodes) {
      if (fwdIn.get(n.id).length === 0) {
        level.set(n.id, 0);
        queue.push(n.id);
      }
    }
    if (queue.length === 0) {
      for (const n of flowNodes) {
        if (n.type === "start") {
          level.set(n.id, 0);
          queue.push(n.id);
        }
      }
    }
    let qi = 0;
    while (qi < queue.length) {
      const cur = queue[qi++];
      const curLevel = level.get(cur);
      for (const next of fwdOut.get(cur) ?? []) {
        const existing = level.get(next) ?? -1;
        if (curLevel + 1 > existing) {
          level.set(next, curLevel + 1);
          queue.push(next);
        }
      }
    }
    for (const n of flowNodes) {
      if (level.has(n.id)) continue;
      const incomingFlows = flows.filter((f) => f.target === n.id);
      for (const f of incomingFlows) {
        const srcNode = nodeMap.get(f.source);
        if (srcNode?.type === "boundary" && srcNode.attachedTo) {
          const parentLevel = level.get(srcNode.attachedTo);
          if (parentLevel !== void 0) {
            level.set(n.id, Math.max(0, parentLevel + 1));
            break;
          }
        }
      }
    }
    for (const n of flowNodes) {
      if (!level.has(n.id)) level.set(n.id, 0);
    }
    const byLevel = /* @__PURE__ */ new Map();
    for (const n of flowNodes) {
      const lv = level.get(n.id);
      if (!byLevel.has(lv)) byLevel.set(lv, []);
      byLevel.get(lv).push(n.id);
    }
    function isRejectionTarget(id) {
      const node = nodeMap.get(id);
      if (!node) return false;
      const text = (node.label + " " + node.id).toLowerCase();
      if (text.includes("\u043E\u0442\u043A\u043B\u043E\u043D") || text.includes("reject") || text.includes("fail") || text.includes("error") || text.includes("cancel")) {
        return true;
      }
      for (const f of flows) {
        if (f.target === id && f.condition) {
          const c = f.condition.toLowerCase();
          if (c.includes("\u043D\u0435\u0442") || c.includes("no") || c.includes("\u043E\u0442\u043A\u043B\u043E\u043D") || c.includes("fail") || c.includes("false")) {
            return true;
          }
        }
      }
      return false;
    }
    const maxLevel = byLevel.size > 0 ? Math.max(...Array.from(byLevel.keys())) : 0;
    for (let lv = 1; lv <= maxLevel; lv++) {
      const ids = byLevel.get(lv) || [];
      if (ids.length <= 1) continue;
      const prevIds = byLevel.get(lv - 1) || [];
      const prevIndex = new Map(prevIds.map((id, idx) => [id, idx]));
      const bary = ids.map((id, originalIdx) => {
        const preds = fwdIn.get(id) || [];
        let sum = 0;
        let count = 0;
        for (const p of preds) {
          if (prevIndex.has(p)) {
            sum += prevIndex.get(p);
            count++;
          } else if (level.get(p) !== void 0 && level.get(p) < lv) {
            const pIds = byLevel.get(level.get(p)) || [];
            const idx = pIds.indexOf(p);
            if (idx !== -1) {
              sum += idx / Math.max(1, pIds.length - 1) * Math.max(1, prevIds.length - 1);
              count++;
            }
          }
        }
        let val = count > 0 ? sum / count : originalIdx;
        if (isRejectionTarget(id)) {
          val += 10;
        }
        return { id, val, originalIdx };
      });
      bary.sort((a, b) => a.val - b.val || a.originalIdx - b.originalIdx);
      byLevel.set(lv, bary.map((b) => b.id));
    }
    for (let lv = maxLevel - 1; lv >= 0; lv--) {
      const ids = byLevel.get(lv) || [];
      if (ids.length <= 1) continue;
      const nextIds = byLevel.get(lv + 1) || [];
      const nextIndex = new Map(nextIds.map((id, idx) => [id, idx]));
      const bary = ids.map((id, originalIdx) => {
        const succs = fwdOut.get(id) || [];
        let sum = 0;
        let count = 0;
        for (const s of succs) {
          if (nextIndex.has(s)) {
            sum += nextIndex.get(s);
            count++;
          } else if (level.get(s) !== void 0 && level.get(s) > lv) {
            const sIds = byLevel.get(level.get(s)) || [];
            const idx = sIds.indexOf(s);
            if (idx !== -1) {
              sum += idx / Math.max(1, sIds.length - 1) * Math.max(1, nextIds.length - 1);
              count++;
            }
          }
        }
        let val = count > 0 ? sum / count : originalIdx;
        if (isRejectionTarget(id)) {
          val += 10;
        }
        return { id, val, originalIdx };
      });
      bary.sort((a, b) => a.val - b.val || a.originalIdx - b.originalIdx);
      byLevel.set(lv, bary.map((b) => b.id));
    }
    const levelMaxWidth = /* @__PURE__ */ new Map();
    for (const [lv, ids] of byLevel) {
      const maxW = Math.max(...ids.map((id) => SIZES[nodeMap.get(id).type]?.w ?? 100));
      levelMaxWidth.set(lv, maxW);
    }
    const hasPools = pools.length > 0;
    const xOffset = hasPools ? PADDING + POOL_HEADER : PADDING;
    const levelX = /* @__PURE__ */ new Map();
    let curX = xOffset;
    for (let lv = 0; lv <= maxLevel; lv++) {
      levelX.set(lv, curX);
      curX += (levelMaxWidth.get(lv) ?? 100) + H_GAP;
    }
    let maxColH = 0;
    for (const [, ids] of byLevel) {
      const sizes = ids.map((id) => SIZES[nodeMap.get(id).type] ?? { w: 100, h: 80 });
      const totalH = sizes.reduce((sum, s) => sum + s.h, 0) + V_GAP * (ids.length - 1);
      maxColH = Math.max(maxColH, totalH);
    }
    const centerBaseline = Math.max(300, maxColH);
    const layoutNodes = [];
    for (const [lv, ids] of byLevel) {
      const x = levelX.get(lv);
      const sizes = ids.map((id) => SIZES[nodeMap.get(id).type] ?? { w: 100, h: 80 });
      const totalH = sizes.reduce((sum, s) => sum + s.h, 0) + V_GAP * (ids.length - 1);
      let curY = PADDING + Math.max(0, (centerBaseline - totalH) / 2);
      for (let i = 0; i < ids.length; i++) {
        const id = ids[i];
        const node = nodeMap.get(id);
        const { w, h } = sizes[i];
        layoutNodes.push({ ...node, x, y: curY, width: w, height: h, level: lv });
        curY += h + V_GAP;
      }
    }
    const layoutNodeMap = new Map(layoutNodes.map((n) => [n.id, n]));
    const boundaryByParent = /* @__PURE__ */ new Map();
    for (const b of boundaryNodes) {
      if (!b.attachedTo) continue;
      if (!boundaryByParent.has(b.attachedTo)) boundaryByParent.set(b.attachedTo, []);
      boundaryByParent.get(b.attachedTo).push(b);
    }
    for (const [parentId, bNodes] of boundaryByParent) {
      const parent = layoutNodeMap.get(parentId);
      if (!parent) continue;
      const bSize = SIZES.boundary;
      const spacing = 44;
      const startX = parent.x + (parent.width - spacing * (bNodes.length - 1)) / 2 - bSize.w / 2;
      for (let i = 0; i < bNodes.length; i++) {
        const b = bNodes[i];
        const bx = startX + spacing * i;
        const by = parent.y + parent.height - bSize.h / 2;
        const ln = { ...b, x: bx, y: by, width: bSize.w, height: bSize.h, level: parent.level };
        layoutNodes.push(ln);
        layoutNodeMap.set(b.id, ln);
      }
    }
    for (const ann of annotationNodes) {
      const target = ann.annotationTarget ? layoutNodeMap.get(ann.annotationTarget) : void 0;
      const aSize = SIZES.annotation;
      const ax = target ? target.x + target.width + 20 : PADDING;
      const ay = target ? target.y - aSize.h - 10 : PADDING;
      const ln = { ...ann, x: ax, y: Math.max(10, ay), width: aSize.w, height: aSize.h, level: target?.level ?? 0 };
      layoutNodes.push(ln);
      layoutNodeMap.set(ann.id, ln);
    }
    if (dataNodes.length > 0) {
      let maxBottom = 0;
      for (const n of layoutNodes) {
        maxBottom = Math.max(maxBottom, n.y + n.height);
      }
      const dataY = maxBottom + V_GAP;
      let dataX = PADDING;
      for (const d of dataNodes) {
        const { w, h } = SIZES[d.type] ?? { w: 50, h: 50 };
        layoutNodes.push({ ...d, x: dataX, y: dataY, width: w, height: h });
        layoutNodeMap.set(d.id, layoutNodes[layoutNodes.length - 1]);
        dataX += w + H_GAP;
      }
    }
    const layoutPools = [];
    const layoutLanes = [];
    if (hasPools) {
      let minX = Infinity, maxX2 = 0, minY = Infinity, maxY2 = 0;
      for (const n of layoutNodes) {
        minX = Math.min(minX, n.x);
        maxX2 = Math.max(maxX2, n.x + n.width);
        minY = Math.min(minY, n.y);
        maxY2 = Math.max(maxY2, n.y + n.height);
      }
      const diagramWidth = Math.max(maxX2 - PADDING + PADDING + POOL_HEADER, 600);
      const diagramHeight = Math.max(maxY2 + PADDING - PADDING, 300);
      for (const pool of pools) {
        const poolLanes = lanes.filter((l) => l.pool === pool.id);
        const poolX = PADDING;
        const poolY = PADDING - 20;
        const poolW = diagramWidth;
        const poolH = diagramHeight + 40;
        layoutPools.push({ id: pool.id, name: pool.name, x: poolX, y: poolY, width: poolW, height: poolH });
        if (poolLanes.length > 0) {
          const laneH = poolH / poolLanes.length;
          for (let i = 0; i < poolLanes.length; i++) {
            layoutLanes.push({
              id: poolLanes[i].id,
              name: poolLanes[i].name,
              pool: pool.id,
              x: poolX,
              y: poolY + laneH * i,
              width: poolW,
              height: laneH
            });
          }
        }
      }
    }
    return { nodes: layoutNodes, flows, pools: layoutPools, lanes: layoutLanes, messageFlows };
  }

  // src/generator.ts
  function escapeXml(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function taskTag(node) {
    if (node.taskType) {
      const map = {
        user: "userTask",
        service: "serviceTask",
        script: "scriptTask",
        send: "sendTask",
        receive: "receiveTask",
        manual: "manualTask",
        businessrule: "businessRuleTask"
      };
      return map[node.taskType] ?? "task";
    }
    return "task";
  }
  function gatewayTag(node) {
    const map = {
      exclusive: "exclusiveGateway",
      parallel: "parallelGateway",
      inclusive: "inclusiveGateway",
      eventbased: "eventBasedGateway"
    };
    return map[node.gatewayType ?? "exclusive"];
  }
  function eventDefinitionXml(node) {
    if (!node.eventType || node.eventType === "none") return "";
    const map = {
      message: "messageEventDefinition",
      timer: "timerEventDefinition",
      signal: "signalEventDefinition",
      error: "errorEventDefinition",
      terminate: "terminateEventDefinition",
      escalation: "escalationEventDefinition",
      compensate: "compensateEventDefinition",
      conditional: "conditionalEventDefinition",
      link: "linkEventDefinition"
    };
    const tag = map[node.eventType];
    return tag ? `<${tag} id="${escapeXml(node.id)}_ed"/>` : "";
  }
  function loopXml(node) {
    if (!node.loopType) return "";
    if (node.loopType === "standard") return "<standardLoopCharacteristics/>";
    const seq = node.loopType === "sequential" ? "true" : "false";
    return `<multiInstanceLoopCharacteristics isSequential="${seq}"/>`;
  }
  function elementXml(node, incoming, outgoing, defaultFlows) {
    const id = escapeXml(node.id);
    const name = escapeXml(node.label);
    const children = [];
    const evDef = eventDefinitionXml(node);
    if (evDef) children.push(evDef);
    const lp = loopXml(node);
    if (lp) children.push(lp);
    if (node.performer) {
      children.push(`<documentation>${escapeXml(node.performer)}</documentation>`);
    }
    for (const inc of incoming) children.push(`<incoming>${inc}</incoming>`);
    for (const out of outgoing) children.push(`<outgoing>${out}</outgoing>`);
    let tag;
    let attrs = `id="${id}" name="${name}"`;
    switch (node.type) {
      case "start":
        tag = "startEvent";
        break;
      case "end":
        tag = "endEvent";
        break;
      case "catch":
        tag = "intermediateCatchEvent";
        break;
      case "throw":
        tag = "intermediateThrowEvent";
        break;
      case "boundary":
        tag = "boundaryEvent";
        attrs += ` attachedToRef="${escapeXml(node.attachedTo ?? "")}"`;
        attrs += ` cancelActivity="${node.interrupting !== false ? "true" : "false"}"`;
        break;
      case "task":
        tag = taskTag(node);
        break;
      case "call":
        tag = "callActivity";
        break;
      case "subprocess":
        tag = "subProcess";
        attrs += ' isExpanded="false"';
        break;
      case "gateway":
        tag = gatewayTag(node);
        if (defaultFlows.has(node.id)) {
          attrs += ` default="${defaultFlows.get(node.id)}"`;
        }
        break;
      case "annotation":
      case "data":
      case "datastore":
        return "";
      default:
        tag = "task";
    }
    if (children.length === 0) {
      return `<${tag} ${attrs}/>`;
    }
    return [`<${tag} ${attrs}>`, ...children.map((c) => "  " + c), `</${tag}>`].join("\n");
  }
  function annotationXml(node) {
    return [
      `<textAnnotation id="${escapeXml(node.id)}">`,
      `  <text>${escapeXml(node.label)}</text>`,
      `</textAnnotation>`
    ].join("\n");
  }
  function associationXml(node, counter) {
    if (!node.annotationTarget) return "";
    return `<association id="Association_${counter}" sourceRef="${escapeXml(node.id)}" targetRef="${escapeXml(node.annotationTarget)}"/>`;
  }
  function dataObjectXml(node) {
    return [
      `<dataObjectReference id="${escapeXml(node.id)}" name="${escapeXml(node.label)}" dataObjectRef="DataObject_${escapeXml(node.id)}"/>`,
      `<dataObject id="DataObject_${escapeXml(node.id)}"/>`
    ].join("\n");
  }
  function dataStoreXml(node) {
    return `<dataStoreReference id="${escapeXml(node.id)}" name="${escapeXml(node.label)}"/>`;
  }
  function flowXml(flow) {
    const cond = flow.condition ? `
  <conditionExpression>${escapeXml(flow.condition)}</conditionExpression>
` : "";
    return `<sequenceFlow id="${flow.id}" sourceRef="${flow.source}" targetRef="${flow.target}">${cond}</sequenceFlow>`;
  }
  function messageFlowXml(mf) {
    const nameAttr = mf.label ? ` name="${escapeXml(mf.label)}"` : "";
    return `<messageFlow id="${mf.id}" sourceRef="${mf.source}" targetRef="${mf.target}"${nameAttr}/>`;
  }
  function shapeXml(node) {
    const bx = Math.round(node.x);
    const by = Math.round(node.y);
    return [
      `<bpmndi:BPMNShape id="${node.id}_di" bpmnElement="${node.id}">`,
      `  <dc:Bounds x="${bx}" y="${by}" width="${node.width}" height="${node.height}"/>`,
      `  <bpmndi:BPMNLabel/>`,
      `</bpmndi:BPMNShape>`
    ].join("\n");
  }
  function poolShapeXml(pool) {
    return [
      `<bpmndi:BPMNShape id="${pool.id}_di" bpmnElement="${pool.id}" isHorizontal="true">`,
      `  <dc:Bounds x="${Math.round(pool.x)}" y="${Math.round(pool.y)}" width="${Math.round(pool.width)}" height="${Math.round(pool.height)}"/>`,
      `  <bpmndi:BPMNLabel/>`,
      `</bpmndi:BPMNShape>`
    ].join("\n");
  }
  function laneShapeXml(lane) {
    return [
      `<bpmndi:BPMNShape id="${lane.id}_di" bpmnElement="${lane.id}" isHorizontal="true">`,
      `  <dc:Bounds x="${Math.round(lane.x)}" y="${Math.round(lane.y)}" width="${Math.round(lane.width)}" height="${Math.round(lane.height)}"/>`,
      `  <bpmndi:BPMNLabel/>`,
      `</bpmndi:BPMNShape>`
    ].join("\n");
  }
  function routeEdgesXml(flows, nodeMap, layoutNodes) {
    if (flows.length === 0) return "";
    const outgoingFlows = /* @__PURE__ */ new Map();
    const incomingFlows = /* @__PURE__ */ new Map();
    for (const f of flows) {
      if (!outgoingFlows.has(f.source)) outgoingFlows.set(f.source, []);
      outgoingFlows.get(f.source).push(f);
      if (!incomingFlows.has(f.target)) incomingFlows.set(f.target, []);
      incomingFlows.get(f.target).push(f);
    }
    const flowPorts = /* @__PURE__ */ new Map();
    for (const [srcId, outList] of outgoingFlows) {
      const src = nodeMap.get(srcId);
      if (!src) continue;
      if (src.type === "gateway") {
        if (outList.length === 1) {
          flowPorts.set(outList[0].id, {
            start: [Math.round(src.x + src.width), Math.round(src.y + src.height / 2), "E"],
            end: [0, 0, "W"]
          });
        } else if (outList.length === 2) {
          const t0 = nodeMap.get(outList[0].target);
          const t1 = nodeMap.get(outList[1].target);
          const y0 = t0 ? t0.y + t0.height / 2 : src.y;
          const y1 = t1 ? t1.y + t1.height / 2 : src.y;
          const srcMidY = src.y + src.height / 2;
          const srcMidX = src.x + src.width / 2;
          let fTop = outList[0];
          let fBot = outList[1];
          if (y0 > y1) {
            fTop = outList[1];
            fBot = outList[0];
          }
          const topTgtY = Math.min(y0, y1);
          const botTgtY = Math.max(y0, y1);
          if (botTgtY > srcMidY + 20 && topTgtY < srcMidY - 20) {
            flowPorts.set(fTop.id, { start: [Math.round(srcMidX), Math.round(src.y), "N"], end: [0, 0, "W"] });
            flowPorts.set(fBot.id, { start: [Math.round(srcMidX), Math.round(src.y + src.height), "S"], end: [0, 0, "W"] });
          } else if (botTgtY > srcMidY + 20) {
            flowPorts.set(fTop.id, { start: [Math.round(src.x + src.width), Math.round(srcMidY), "E"], end: [0, 0, "W"] });
            flowPorts.set(fBot.id, { start: [Math.round(srcMidX), Math.round(src.y + src.height), "S"], end: [0, 0, "W"] });
          } else if (topTgtY < srcMidY - 20) {
            flowPorts.set(fTop.id, { start: [Math.round(srcMidX), Math.round(src.y), "N"], end: [0, 0, "W"] });
            flowPorts.set(fBot.id, { start: [Math.round(src.x + src.width), Math.round(srcMidY), "E"], end: [0, 0, "W"] });
          } else {
            flowPorts.set(fTop.id, { start: [Math.round(src.x + src.width), Math.round(srcMidY - 8), "E"], end: [0, 0, "W"] });
            flowPorts.set(fBot.id, { start: [Math.round(src.x + src.width), Math.round(srcMidY + 8), "E"], end: [0, 0, "W"] });
          }
        } else {
          const sorted = [...outList].sort((a, b) => {
            const ya = nodeMap.get(a.target)?.y ?? 0;
            const yb = nodeMap.get(b.target)?.y ?? 0;
            return ya - yb;
          });
          const srcMidX = Math.round(src.x + src.width / 2);
          flowPorts.set(sorted[0].id, { start: [srcMidX, Math.round(src.y), "N"], end: [0, 0, "W"] });
          flowPorts.set(sorted[sorted.length - 1].id, { start: [srcMidX, Math.round(src.y + src.height), "S"], end: [0, 0, "W"] });
          for (let i = 1; i < sorted.length - 1; i++) {
            const frac = i / (sorted.length - 1);
            const ey = Math.round(src.y + src.height * frac);
            flowPorts.set(sorted[i].id, { start: [Math.round(src.x + src.width), ey, "E"], end: [0, 0, "W"] });
          }
        }
      } else {
        if (outList.length === 1) {
          flowPorts.set(outList[0].id, {
            start: [Math.round(src.x + src.width), Math.round(src.y + src.height / 2), "E"],
            end: [0, 0, "W"]
          });
        } else {
          const sorted = [...outList].sort((a, b) => (nodeMap.get(a.target)?.y ?? 0) - (nodeMap.get(b.target)?.y ?? 0));
          for (let i = 0; i < sorted.length; i++) {
            const frac = (i + 1) / (sorted.length + 1);
            const ey = Math.round(src.y + src.height * frac);
            flowPorts.set(sorted[i].id, {
              start: [Math.round(src.x + src.width), ey, "E"],
              end: [0, 0, "W"]
            });
          }
        }
      }
    }
    for (const [tgtId, inList] of incomingFlows) {
      const tgt = nodeMap.get(tgtId);
      if (!tgt) continue;
      if (tgt.type === "gateway") {
        if (inList.length === 1) {
          const fp = flowPorts.get(inList[0].id);
          if (fp) fp.end = [Math.round(tgt.x), Math.round(tgt.y + tgt.height / 2), "W"];
        } else if (inList.length === 2) {
          const s0 = nodeMap.get(inList[0].source);
          const s1 = nodeMap.get(inList[1].source);
          const y0 = s0 ? s0.y + s0.height / 2 : tgt.y;
          const y1 = s1 ? s1.y + s1.height / 2 : tgt.y;
          const tgtMidY = tgt.y + tgt.height / 2;
          const tgtMidX = tgt.x + tgt.width / 2;
          let fTop = inList[0];
          let fBot = inList[1];
          if (y0 > y1) {
            fTop = inList[1];
            fBot = inList[0];
          }
          const topSrcY = Math.min(y0, y1);
          const botSrcY = Math.max(y0, y1);
          const fpTop = flowPorts.get(fTop.id);
          const fpBot = flowPorts.get(fBot.id);
          if (botSrcY > tgtMidY + 20 && topSrcY < tgtMidY - 20) {
            if (fpTop) fpTop.end = [Math.round(tgtMidX), Math.round(tgt.y), "N"];
            if (fpBot) fpBot.end = [Math.round(tgtMidX), Math.round(tgt.y + tgt.height), "S"];
          } else if (topSrcY < tgtMidY - 20) {
            if (fpTop) fpTop.end = [Math.round(tgtMidX), Math.round(tgt.y), "N"];
            if (fpBot) fpBot.end = [Math.round(tgt.x), Math.round(tgtMidY), "W"];
          } else if (botSrcY > tgtMidY + 20) {
            if (fpTop) fpTop.end = [Math.round(tgt.x), Math.round(tgtMidY), "W"];
            if (fpBot) fpBot.end = [Math.round(tgtMidX), Math.round(tgt.y + tgt.height), "S"];
          } else {
            if (fpTop) fpTop.end = [Math.round(tgt.x), Math.round(tgtMidY - 8), "W"];
            if (fpBot) fpBot.end = [Math.round(tgt.x), Math.round(tgtMidY + 8), "W"];
          }
        } else {
          const sorted = [...inList].sort((a, b) => (nodeMap.get(a.source)?.y ?? 0) - (nodeMap.get(b.source)?.y ?? 0));
          const tgtMidX = Math.round(tgt.x + tgt.width / 2);
          const fp0 = flowPorts.get(sorted[0].id);
          if (fp0) fp0.end = [tgtMidX, Math.round(tgt.y), "N"];
          const fpLast = flowPorts.get(sorted[sorted.length - 1].id);
          if (fpLast) fpLast.end = [tgtMidX, Math.round(tgt.y + tgt.height), "S"];
          for (let i = 1; i < sorted.length - 1; i++) {
            const frac = i / (sorted.length - 1);
            const ey = Math.round(tgt.y + tgt.height * frac);
            const fpi = flowPorts.get(sorted[i].id);
            if (fpi) fpi.end = [Math.round(tgt.x), ey, "W"];
          }
        }
      } else {
        if (inList.length === 1) {
          const fp = flowPorts.get(inList[0].id);
          if (fp) fp.end = [Math.round(tgt.x), Math.round(tgt.y + tgt.height / 2), "W"];
        } else {
          const sorted = [...inList].sort((a, b) => (nodeMap.get(a.source)?.y ?? 0) - (nodeMap.get(b.source)?.y ?? 0));
          for (let i = 0; i < sorted.length; i++) {
            const frac = (i + 1) / (sorted.length + 1);
            const ey = Math.round(tgt.y + tgt.height * frac);
            const fp = flowPorts.get(sorted[i].id);
            if (fp) fp.end = [Math.round(tgt.x), ey, "W"];
          }
        }
      }
    }
    const gapVerticals = /* @__PURE__ */ new Map();
    const loopFlows = [];
    const skipCorridorFlows = [];
    for (const f of flows) {
      const src = nodeMap.get(f.source);
      const tgt = nodeMap.get(f.target);
      if (!src || !tgt) continue;
      const ports = flowPorts.get(f.id);
      if (!ports) continue;
      const [x1, ,] = ports.start;
      const [x2, ,] = ports.end;
      if (x2 < x1 - 10) {
        loopFlows.push(f);
      } else {
        const srcCol = src.level ?? 0;
        const tgtCol = tgt.level ?? 0;
        if (tgtCol > srcCol + 1) {
          skipCorridorFlows.push(f);
        } else {
          const gapKey = srcCol;
          if (!gapVerticals.has(gapKey)) gapVerticals.set(gapKey, []);
          gapVerticals.get(gapKey).push(f);
        }
      }
    }
    const flowBendX = /* @__PURE__ */ new Map();
    for (const [, fList] of gapVerticals) {
      fList.sort((a, b) => {
        const sa = nodeMap.get(a.source);
        const sb = nodeMap.get(b.source);
        return (sa?.y ?? 0) - (sb?.y ?? 0);
      });
      for (let i = 0; i < fList.length; i++) {
        const f = fList[i];
        const ports = flowPorts.get(f.id);
        const x1 = ports.start[0];
        const x2 = ports.end[0];
        const channelOffset = 22 + i % 4 * 16;
        const bx = Math.min(x2 - 12, Math.max(x1 + 14, x1 + channelOffset));
        flowBendX.set(f.id, Math.round(bx));
      }
    }
    let minDiagramY = Infinity;
    let maxDiagramY = -Infinity;
    for (const n of layoutNodes) {
      if (n.y < minDiagramY) minDiagramY = n.y;
      if (n.y + n.height > maxDiagramY) maxDiagramY = n.y + n.height;
    }
    if (!isFinite(minDiagramY)) minDiagramY = 80;
    if (!isFinite(maxDiagramY)) maxDiagramY = 400;
    const topCorridorFlows = [];
    const bottomCorridorFlows = [];
    for (const f of skipCorridorFlows) {
      const tgt = nodeMap.get(f.target);
      const isTop = tgt && tgt.y + tgt.height / 2 < (minDiagramY + maxDiagramY) / 2;
      if (isTop) topCorridorFlows.push(f);
      else bottomCorridorFlows.push(f);
    }
    const flowCorridorY = /* @__PURE__ */ new Map();
    for (let i = 0; i < topCorridorFlows.length; i++) {
      const f = topCorridorFlows[i];
      flowCorridorY.set(f.id, Math.round(Math.max(20, minDiagramY - 35 - i * 16)));
    }
    for (let i = 0; i < bottomCorridorFlows.length; i++) {
      const f = bottomCorridorFlows[i];
      flowCorridorY.set(f.id, Math.round(maxDiagramY + 35 + i * 16));
    }
    const flowLoopY = /* @__PURE__ */ new Map();
    for (let i = 0; i < loopFlows.length; i++) {
      const f = loopFlows[i];
      flowLoopY.set(f.id, Math.round(maxDiagramY + 40 + (bottomCorridorFlows.length + i) * 20));
    }
    const edgeXmls = [];
    for (const f of flows) {
      const src = nodeMap.get(f.source);
      const tgt = nodeMap.get(f.target);
      if (!src || !tgt) continue;
      const ports = flowPorts.get(f.id);
      if (!ports) continue;
      const [x1, y1, sSide] = ports.start;
      const [x2, y2, eSide] = ports.end;
      let pts = [];
      if (x2 < x1 - 10) {
        const loopY = flowLoopY.get(f.id) ?? maxDiagramY + 50;
        pts = [
          [x1, y1],
          [x1, loopY],
          [x2, loopY],
          [x2, y2]
        ];
      } else if (flowCorridorY.has(f.id)) {
        const corridorY = flowCorridorY.get(f.id);
        const approachX = Math.round(x2 - 18 - skipCorridorFlows.indexOf(f) % 3 * 14);
        if (sSide === "N" || sSide === "S") {
          pts = [
            [x1, y1],
            [x1, corridorY],
            [approachX, corridorY],
            [approachX, y2],
            [x2, y2]
          ];
        } else {
          const exitBendX = Math.round(x1 + 18);
          pts = [
            [x1, y1],
            [exitBendX, y1],
            [exitBendX, corridorY],
            [approachX, corridorY],
            [approachX, y2],
            [x2, y2]
          ];
        }
      } else {
        if (sSide === "N" || sSide === "S") {
          if (eSide === "N" || eSide === "S") {
            pts = [
              [x1, y1],
              [x2, y1],
              [x2, y2]
            ];
          } else {
            if (sSide === "N" && y2 <= y1 || sSide === "S" && y2 >= y1) {
              pts = [
                [x1, y1],
                [x1, y2],
                [x2, y2]
              ];
            } else {
              const bendX = flowBendX.get(f.id) ?? Math.round(x1 + (x2 - x1) / 2);
              pts = [
                [x1, y1],
                [bendX, y1],
                [bendX, y2],
                [x2, y2]
              ];
            }
          }
        } else if (eSide === "N" || eSide === "S") {
          pts = [
            [x1, y1],
            [x2, y1],
            [x2, y2]
          ];
        } else {
          if (Math.abs(y1 - y2) < 4) {
            pts = [[x1, y1], [x2, y2]];
          } else {
            const bendX = flowBendX.get(f.id) ?? Math.round(x1 + (x2 - x1) / 2);
            pts = [
              [x1, y1],
              [bendX, y1],
              [bendX, y2],
              [x2, y2]
            ];
          }
        }
      }
      const cleanPts = [];
      for (let i = 0; i < pts.length; i++) {
        const p = pts[i];
        if (cleanPts.length > 0) {
          const prev = cleanPts[cleanPts.length - 1];
          if (prev[0] === p[0] && prev[1] === p[1]) continue;
        }
        cleanPts.push(p);
      }
      const waypointXml = cleanPts.map(([x, y]) => `  <di:waypoint x="${x}" y="${y}"/>`);
      const condition = "condition" in f ? f.condition : void 0;
      let labelXml = [];
      if (condition) {
        let lx = cleanPts[0][0] + 8;
        let ly = cleanPts[0][1] - 18;
        if (sSide === "S") {
          ly = cleanPts[0][1] + 6;
        } else if (sSide === "N") {
          ly = cleanPts[0][1] - 20;
        }
        labelXml = [
          `  <bpmndi:BPMNLabel><dc:Bounds x="${lx}" y="${ly}" width="${condition.length * 7 + 4}" height="14"/></bpmndi:BPMNLabel>`
        ];
      }
      edgeXmls.push([
        `<bpmndi:BPMNEdge id="${f.id}_di" bpmnElement="${f.id}">`,
        ...waypointXml,
        ...labelXml,
        `</bpmndi:BPMNEdge>`
      ].join("\n"));
    }
    return edgeXmls.join("\n");
  }
  function associationEdgeXml(annNode, targetNode, counter) {
    const x1 = Math.round(annNode.x + annNode.width / 2);
    const y1 = Math.round(annNode.y + annNode.height);
    const x2 = Math.round(targetNode.x + targetNode.width / 2);
    const y2 = Math.round(targetNode.y);
    return [
      `<bpmndi:BPMNEdge id="Association_${counter}_di" bpmnElement="Association_${counter}">`,
      `  <di:waypoint x="${x1}" y="${y1}"/>`,
      `  <di:waypoint x="${x2}" y="${y2}"/>`,
      `</bpmndi:BPMNEdge>`
    ].join("\n");
  }
  function generate(process) {
    const result = layout(process);
    const { nodes: layoutNodes, flows, pools, lanes, messageFlows } = result;
    const nodeMap = new Map(layoutNodes.map((n) => [n.id, n]));
    const flowElements = layoutNodes.filter(
      (n) => n.type !== "annotation" && n.type !== "data" && n.type !== "datastore"
    );
    const incomingMap = new Map(flowElements.map((n) => [n.id, []]));
    const outgoingMap = new Map(flowElements.map((n) => [n.id, []]));
    for (const f of flows) {
      incomingMap.get(f.target)?.push(f.id);
      outgoingMap.get(f.source)?.push(f.id);
    }
    const defaultFlows = /* @__PURE__ */ new Map();
    for (const f of flows) {
      if (f.isDefault) {
        defaultFlows.set(f.source, f.id);
      }
    }
    const hasPools = pools.length > 0;
    const processId = "Process_1";
    const elements = flowElements.map((n) => elementXml(n, incomingMap.get(n.id) ?? [], outgoingMap.get(n.id) ?? [], defaultFlows)).filter((s) => s.length > 0).join("\n");
    const seqFlows = flows.map(flowXml).join("\n");
    const annotations = layoutNodes.filter((n) => n.type === "annotation");
    let assocCounter = 1;
    const annotationElements = annotations.map((n) => annotationXml(n)).join("\n");
    const associationElements = annotations.map((n) => associationXml(n, assocCounter++)).filter((s) => s.length > 0).join("\n");
    const dataNodes = layoutNodes.filter((n) => n.type === "data");
    const dataStoreNodes = layoutNodes.filter((n) => n.type === "datastore");
    const dataElements = dataNodes.map((n) => dataObjectXml(n)).join("\n");
    const dataStoreElements = dataStoreNodes.map((n) => dataStoreXml(n)).join("\n");
    let laneSetXml = "";
    if (lanes.length > 0) {
      const laneEntries = lanes.map((lane) => {
        const refs = layoutNodes.filter((n) => n.laneId === lane.id).map((n) => `    <flowNodeRef>${escapeXml(n.id)}</flowNodeRef>`).join("\n");
        const body = refs ? `
${refs}
  ` : "";
        return `<lane id="${escapeXml(lane.id)}" name="${escapeXml(lane.name)}">${body}</lane>`;
      }).join("\n");
      laneSetXml = `<laneSet id="LaneSet_1">
${laneEntries}
</laneSet>`;
    }
    function indent(text, level) {
      if (!text) return "";
      const pad = "  ".repeat(level);
      return text.split("\n").map((l) => pad + l).join("\n");
    }
    const processContent = [
      laneSetXml,
      elements,
      seqFlows,
      annotationElements,
      associationElements,
      dataElements,
      dataStoreElements
    ].filter((s) => s.length > 0).map((s) => indent(s, 2)).join("\n");
    let collaborationXml = "";
    if (hasPools) {
      const participants = pools.map(
        (p) => `    <participant id="${escapeXml(p.id)}" name="${escapeXml(p.name)}" processRef="${processId}"/>`
      ).join("\n");
      const msgFlows = messageFlows.length > 0 ? "\n" + messageFlows.map((mf) => "    " + messageFlowXml(mf)).join("\n") : "";
      collaborationXml = `
  <collaboration id="Collaboration_1">
${participants}${msgFlows}
  </collaboration>
`;
    } else if (messageFlows.length > 0) {
      const msgFlows = messageFlows.map((mf) => "    " + messageFlowXml(mf)).join("\n");
      collaborationXml = `
  <collaboration id="Collaboration_1">
    <participant id="Participant_1" name="${escapeXml(process.name)}" processRef="${processId}"/>
${msgFlows}
  </collaboration>
`;
    }
    const shapes = layoutNodes.map((n) => shapeXml(n)).join("\n");
    const edges = routeEdgesXml(flows, nodeMap, layoutNodes);
    const poolShapes = pools.length > 0 ? "\n" + result.pools.map((p) => poolShapeXml(p)).join("\n") : "";
    const laneShapes = result.lanes.length > 0 ? "\n" + result.lanes.map((l) => laneShapeXml(l)).join("\n") : "";
    const msgFlowEdges = messageFlows.length > 0 ? "\n" + routeEdgesXml(messageFlows, nodeMap, layoutNodes) : "";
    assocCounter = 1;
    const assocEdges = annotations.map((n) => {
      const target = n.annotationTarget ? nodeMap.get(n.annotationTarget) : void 0;
      if (!target) return "";
      return associationEdgeXml(n, target, assocCounter++);
    }).filter((s) => s.length > 0).join("\n");
    const assocEdgesStr = assocEdges ? "\n" + assocEdges : "";
    const planeElement = hasPools ? "Collaboration_1" : processId;
    return `<?xml version="1.0" encoding="UTF-8"?>
<definitions
  xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
  xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
  xmlns:di="http://www.omg.org/spec/DD/20100524/DI"
  targetNamespace="http://bpmn-as-code/schema"
  xsi:schemaLocation="http://www.omg.org/spec/BPMN/20100524/MODEL http://www.omg.org/spec/BPMN/2.0/20100501/BPMN20.xsd">
${collaborationXml}
  <process id="${processId}" name="${escapeXml(process.name)}" isExecutable="false">
${processContent}
  </process>

  <bpmndi:BPMNDiagram id="BPMNDiagram_1">
    <bpmndi:BPMNPlane id="BPMNPlane_1" bpmnElement="${planeElement}">${poolShapes}${laneShapes}
${indent(shapes, 3)}
${indent(edges, 3)}${msgFlowEdges ? "\n" + indent(msgFlowEdges, 3) : ""}${assocEdgesStr ? "\n" + indent(assocEdgesStr, 3) : ""}
    </bpmndi:BPMNPlane>
  </bpmndi:BPMNDiagram>

</definitions>
`;
  }

  // src/browser.ts
  function compile(source) {
    try {
      const ast = parse(source);
      const xml = generate(ast);
      return { valid: true, xml, ast, nodeCount: ast.nodes.length, flowCount: ast.flows.length };
    } catch (err) {
      if (err instanceof ParseErrors) {
        const first = err.errors[0];
        return { valid: false, error: err.message, line: first.line, col: first.col };
      }
      if (err instanceof ParseError) {
        return { valid: false, error: err.message, line: err.line, col: err.col };
      }
      return { valid: false, error: String(err) };
    }
  }
  var DSL_PLACEHOLDER = `process "My Workflow"

start: begin "Start"
end: done "Done"

task: step1 "First Task" user by "Agent"
task: step2 "Second Task" service
gateway: check "Check Result" exclusive

begin -> step1 -> step2 -> check
check --[success]--> done
check --[retry]--> step1

# Task types: user | service | script | send | receive | manual | businessrule
# Event types: message | timer | signal | error | terminate | escalation | compensate | conditional | link
# Gateway types: exclusive | parallel | inclusive | eventbased`;
  return __toCommonJS(browser_exports);
})();
