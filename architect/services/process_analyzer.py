import re
from typing import Any

NODE_PATTERN = re.compile(
    r'^(start|end|catch|throw|boundary|task|gateway|gate|subprocess|call):\s*([a-zA-Z0-9_]+)\s*(?:"([^"]*)")?(.*)$',
    re.MULTILINE
)

FLOW_PATTERN = re.compile(
    r'([a-zA-Z0-9_]+)\s*(--\[(.*?)\]-->|==>|->|~>)\s*([a-zA-Z0-9_]+)'
)


def parse_dsl_structure(dsl_code: str) -> dict[str, Any]:
    """
    Parses DSL code into lightweight AST containing nodes, lanes, pools, and flows.
    """
    nodes = []
    node_map = {}
    lanes = []
    pools = []
    flows = []
    lines = dsl_code.split('\n') if dsl_code else []

    for line_idx, line in enumerate(lines, start=1):
        clean_line = line.split('#')[0].strip()
        if not clean_line:
            continue

        # Pools: pool: p_id "Name"
        if clean_line.startswith('pool:'):
            m = re.match(r'^pool:\s*([a-zA-Z0-9_]+)\s*(?:"([^"]*)")?', clean_line)
            if m:
                pools.append({'id': m.group(1), 'name': m.group(2) or m.group(1), 'line': line_idx})
            continue

        # Lanes: lane: l_id "Name" in p_id
        if clean_line.startswith('lane:'):
            m = re.match(r'^lane:\s*([a-zA-Z0-9_]+)\s*(?:"([^"]*)")?(?:\s+in\s+([a-zA-Z0-9_]+))?', clean_line)
            if m:
                lanes.append({
                    'id': m.group(1),
                    'name': m.group(2) or m.group(1),
                    'pool': m.group(3) or '',
                    'line': line_idx
                })
            continue

        # Nodes
        m_node = NODE_PATTERN.match(clean_line)
        if m_node:
            ntype = m_node.group(1)
            if ntype == 'gate':
                ntype = 'gateway'
            nid = m_node.group(2)
            nlabel = m_node.group(3) or nid
            rest = m_node.group(4) or ''

            lane_m = re.search(r'\bin\s+([a-zA-Z0-9_]+)', rest)
            by_m = re.search(r'\bby\s+"([^"]*)"', rest)
            node_data = {
                'id': nid,
                'type': ntype,
                'label': nlabel,
                'lane': lane_m.group(1) if lane_m else '',
                'performer': by_m.group(1) if by_m else '',
                'line': line_idx,
                'raw': clean_line
            }
            nodes.append(node_data)
            node_map[nid] = node_data
            continue

        # Flows (e.g., a -> b -> c)
        for m_flow in FLOW_PATTERN.finditer(clean_line):
            src = m_flow.group(1)
            arrow = m_flow.group(2)
            cond = m_flow.group(3) or ''
            tgt = m_flow.group(4)
            is_default = '==>' in arrow
            flows.append({
                'source': src,
                'target': tgt,
                'condition': cond.strip(),
                'is_default': is_default,
                'line': line_idx
            })

    return {
        'nodes': nodes,
        'node_map': node_map,
        'lanes': lanes,
        'pools': pools,
        'flows': flows
    }


def find_cycles_and_gaps(structure: dict[str, Any]) -> tuple[list[str], list[str]]:
    """
    Detects rework loops (cycles) and logical gaps (disconnected or orphan nodes).
    """
    node_map = structure['node_map']
    flows = structure['flows']

    # Build adjacency
    adj = {nid: [] for nid in node_map}
    in_degrees = {nid: 0 for nid in node_map}
    out_degrees = {nid: 0 for nid in node_map}

    for f in flows:
        src = f['source']
        tgt = f['target']
        if src in adj and tgt in node_map:
            adj[src].append(tgt)
            out_degrees[src] += 1
            in_degrees[tgt] += 1

    # Detect cycles via DFS
    visited = set()
    recursion_stack = set()
    cycles = []

    def dfs(node: str, path: list[str]):
        visited.add(node)
        recursion_stack.add(node)
        path.append(node)

        for neighbor in adj.get(node, []):
            if neighbor not in visited:
                dfs(neighbor, path)
            elif neighbor in recursion_stack:
                cycle_start_idx = path.index(neighbor)
                cycle_nodes = path[cycle_start_idx:] + [neighbor]
                cycle_repr = " ➔ ".join(cycle_nodes)
                if cycle_repr not in cycles:
                    cycles.append(cycle_repr)

        path.pop()
        recursion_stack.remove(node)

    for nid in node_map:
        if nid not in visited:
            dfs(nid, [])

    # Detect logical gaps (disconnected nodes or missing transitions between steps)
    gaps = []
    hanging_outgoing = []
    hanging_incoming = []
    for nid, node in node_map.items():
        ntype = node['type']
        label = node['label']
        if ntype not in ('start', 'boundary') and in_degrees[nid] == 0 and out_degrees[nid] == 0:
            gaps.append(f"Изолированный шаг «{label}» ({nid}) не имеет связей")
        elif ntype not in ('start', 'boundary') and in_degrees[nid] == 0:
            hanging_incoming.append((nid, label))
        elif ntype not in ('end',) and out_degrees[nid] == 0:
            hanging_outgoing.append((nid, label))

    # If we have pairs of disconnected steps (e.g. step A ended without flow, and step B started without flow)
    paired_count = min(len(hanging_outgoing), len(hanging_incoming))
    for i in range(paired_count):
        out_nid, out_label = hanging_outgoing[i]
        in_nid, in_label = hanging_incoming[i]
        gaps.append(f"между шагом «{out_label}» ({out_nid}) и шагом «{in_label}» ({in_nid}) отсутствует условие перехода")

    for j in range(paired_count, len(hanging_outgoing)):
        out_nid, out_label = hanging_outgoing[j]
        gaps.append(f"У шага «{out_label}» ({out_nid}) отсутствует исходящий переход")

    for k in range(paired_count, len(hanging_incoming)):
        in_nid, in_label = hanging_incoming[k]
        gaps.append(f"У шага «{in_label}» ({in_nid}) отсутствует входящий переход")

    return cycles, gaps


def analyze_process_metrics(structure: dict[str, Any]) -> dict[str, Any]:
    """
    Computes summary metrics for process validation.
    """
    nodes = structure['nodes']
    lanes = structure['lanes']
    cycles, gaps = find_cycles_and_gaps(structure)

    starts = sum(1 for n in nodes if n['type'] == 'start')
    ends = sum(1 for n in nodes if n['type'] == 'end')
    tasks = sum(1 for n in nodes if n['type'] in ('task', 'subprocess', 'call'))
    gateways = sum(1 for n in nodes if n['type'] == 'gateway')

    lane_names = [l['name'] for l in lanes]

    if cycles:
        rework_text = f"{len(cycles)} (напр. {cycles[0]})"
    else:
        rework_text = "циклов доработки не обнаружено"

    if gaps:
        gaps_text = f"обнаружено {len(gaps)} разрыв(а) — {'; '.join(gaps[:2])}"
    else:
        gaps_text = "разрывов не обнаружено"

    return {
        'starts': starts,
        'ends': ends,
        'tasks': tasks,
        'gateways': gateways,
        'lanes_count': len(lanes),
        'lane_names': lane_names,
        'cycles': cycles,
        'rework_summary': rework_text,
        'gaps': gaps,
        'gaps_summary': gaps_text
    }


def generate_validation_report(structure: dict[str, Any]) -> str:
    """
    Builds the concise, expert-approved validation report block.
    """
    metrics = analyze_process_metrics(structure)
    lanes_str = f"{metrics['lanes_count']} ({', '.join(metrics['lane_names'])})" if metrics['lanes_count'] > 0 else "0 (без дорожек)"

    lines = [
        "📊 **Отчет валидации процесса:**",
        f"- 🏁 Стартов: {metrics['starts']} | 🎯 Исходов: {metrics['ends']} | 📋 Задач: {metrics['tasks']} | 🔀 Развилок: {metrics['gateways']}",
        f"- 👥 Ролей/дорожек: {lanes_str}",
        f"- 🔄 Циклов доработки: {metrics['rework_summary']}",
        f"- 🔍 Логическая целостность: {metrics['gaps_summary']}"
    ]
    return "\n".join(lines)


def generate_proactive_questions(structure: dict[str, Any], source_text: str = '') -> list[str]:
    """
    Identifies underspecified areas (missing rejection branches, missing roles, gaps)
    and formulates 1-2 targeted clarifying questions.
    """
    node_map = structure['node_map']
    flows = structure['flows']
    lanes = structure['lanes']
    questions = []

    # 1. Check exclusive gateways with missing rejection/alternative branches
    gw_outgoing = {}
    for f in flows:
        gw_outgoing.setdefault(f['source'], []).append(f)

    for nid, node in node_map.items():
        if node['type'] == 'gateway':
            out_flows = gw_outgoing.get(nid, [])
            conditions = [f['condition'].lower() for f in out_flows if f.get('condition')]
            # Single branch gateway or only positive branch ("да", "согласовано")
            has_positive = any('да' in c or 'соглас' in c or 'одобр' in c or 'yes' in c for c in conditions)
            has_negative = any('нет' in c or 'отклон' in c or 'отказ' in c or 'доработ' in c or 'no' in c for c in conditions)

            if len(out_flows) <= 1 or (has_positive and not has_negative):
                questions.append(
                    f"Что происходит при отрицательном решении на шаге «{node['label']}» (предусмотрен ли отказ или возврат на доработку)?"
                )

    # 2. Check tasks without assigned roles/lanes (if lanes exist)
    if lanes:
        for nid, node in node_map.items():
            if node['type'] == 'task' and not node['lane'] and not node['performer']:
                questions.append(
                    f"Какая роль или подразделение отвечает за выполнение задачи «{node['label']}»?"
                )
                if len(questions) >= 2:
                    break

    # 3. Check disconnected nodes / gaps
    cycles, gaps = find_cycles_and_gaps(structure)
    for g in gaps:
        if len(questions) >= 2:
            break
        m_pair = re.search(r'между шагом «([^»]+)»[^(]*\([^)]+\)\s+и\s+шагом «([^»]+)»', g)
        if m_pair:
            questions.append(
                f"Какое условие или промежуточный шаг связывает «{m_pair.group(1)}» и «{m_pair.group(2)}»?"
            )
            continue
        m = re.search(r'«([^»]+)»', g)
        if m:
            questions.append(
                f"Какое условие или предшествующий шаг инициирует выполнение действия «{m.group(1)}»?"
            )

    return questions[:2]


def extract_traceability(dsl_code: str, source_text: str, trace_hints: list[dict] = None) -> list[dict[str, Any]]:
    """
    Builds traceability mapping between diagram elements, DSL lines, and source prompt sentences.
    """
    structure = parse_dsl_structure(dsl_code)
    nodes = structure['nodes']

    hints_map = {}
    if trace_hints:
        for h in trace_hints:
            if isinstance(h, dict) and 'id' in h:
                hints_map[h['id']] = h.get('quote') or h.get('text') or ''

    # Clean sentences from source text
    raw_sentences = re.split(r'[\r\n]+|[.!?]+', source_text) if source_text else []
    sentences = [s.strip() for s in raw_sentences if len(s.strip()) > 3]

    mappings = []

    for node in nodes:
        nid = node['id']
        label = node['label']
        quote = hints_map.get(nid, '')

        if not quote and sentences:
            # Word overlap heuristic
            words = [w.lower() for w in re.findall(r'[a-zA-Zа-яА-ЯёЁ0-9]{3,}', label)]
            best_score = 0
            best_sentence = ""
            for sent in sentences:
                sent_lower = sent.lower()
                score = sum(1 for w in words if w in sent_lower)
                if score > best_score:
                    best_score = score
                    best_sentence = sent

            if best_score > 0 and best_sentence:
                quote = best_sentence
            else:
                quote = label
        elif not quote:
            quote = label

        mappings.append({
            'id': nid,
            'type': node['type'],
            'label': label,
            'lane': node['lane'],
            'line': node['line'],
            'quote': quote
        })

    return mappings
