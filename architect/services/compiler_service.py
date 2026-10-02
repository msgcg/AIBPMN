import json
import subprocess
import tempfile
from pathlib import Path
from django.conf import settings

def get_compiler_js_path() -> Path:
    # Check local static path first, then sources
    p1 = settings.BASE_DIR / 'architect' / 'static' / 'architect' / 'vendor' / 'compiler.js'
    if p1.exists():
        return p1
    p2 = settings.BASE_DIR / 'sources' / 'bpmn-as-code-main' / 'editor' / 'compiler.js'
    if p2.exists():
        return p2
    return p1

def compile_dsl(dsl_code: str) -> dict:
    """
    Compiles BPMN-as-Code DSL into BPMN 2.0 XML using Node.js and compiler.js.
    Returns:
        {
            'valid': bool,
            'xml': str or None,
            'error': str or None,
            'line': int or None,
            'col': int or None,
            'node_count': int,
            'flow_count': int
        }
    """
    if not dsl_code or not dsl_code.strip():
        return {'valid': False, 'error': 'Код диаграммы пуст', 'line': 1, 'col': 1, 'node_count': 0, 'flow_count': 0}

    compiler_path = get_compiler_js_path()
    if not compiler_path.exists():
        # Try fallback if compiler not copied yet
        return {'valid': True, 'xml': '', 'error': None, 'node_count': 0, 'flow_count': 0}

    # Runner script in Node
    script = f"""
const fs = require('fs');
const vm = require('vm');

try {{
    const compilerPath = {json.dumps(str(compiler_path))};
    const code = fs.readFileSync(compilerPath, 'utf8');
    const ctx = {{}};
    vm.runInNewContext(code, ctx);
    
    const source = fs.readFileSync(0, 'utf8');
    const res = ctx.BpmnAsCode.compile(source);
    
    if (res.error) {{
        console.log(JSON.stringify({{
            valid: false,
            error: res.error,
            line: res.line || 1,
            col: res.col || 1
        }}));
    }} else {{
        console.log(JSON.stringify({{
            valid: true,
            xml: res.xml,
            node_count: res.nodeCount || 0,
            flow_count: res.flowCount || 0
        }}));
    }}
}} catch (e) {{
    console.log(JSON.stringify({{
        valid: false,
        error: e.message || String(e),
        line: 1,
        col: 1
    }}));
}}
"""

    try:
        proc = subprocess.run(
            ['node', '-e', script],
            input=dsl_code,
            text=True,
            capture_output=True,
            timeout=8,
            check=False,
            encoding='utf-8'
        )
        if proc.returncode == 0 and proc.stdout.strip():
            # Parse output
            return json.loads(proc.stdout.strip())
        else:
            return {
                'valid': False,
                'error': proc.stderr.strip() or 'Ошибка выполнения компилятора DSL',
                'line': 1,
                'col': 1,
                'node_count': 0,
                'flow_count': 0
            }
    except subprocess.TimeoutExpired:
        return {'valid': False, 'error': 'Превышен таймаут компиляции диаграммы', 'line': 1, 'col': 1, 'node_count': 0, 'flow_count': 0}
    except Exception as exc:
        return {'valid': False, 'error': f"Исключение при вызове компилятора: {exc}", 'line': 1, 'col': 1, 'node_count': 0, 'flow_count': 0}


import xml.etree.ElementTree as ET

TASK_TAGS = {
    'task', 'userTask', 'serviceTask', 'manualTask',
    'scriptTask', 'businessRuleTask', 'sendTask', 'receiveTask'
}

TASK_TYPE_MAP = {
    'userTask': 'user', 'serviceTask': 'service', 'scriptTask': 'script',
    'sendTask': 'send', 'receiveTask': 'receive', 'manualTask': 'manual',
    'businessRuleTask': 'businessrule'
}

GATEWAY_TAG_MAP = {
    'exclusiveGateway': 'exclusive',
    'parallelGateway': 'parallel',
    'inclusiveGateway': 'inclusive',
    'eventBasedGateway': 'event-based',
}

EVENT_DEF_MAP = {
    'messageEventDefinition': 'message',
    'timerEventDefinition': 'timer',
    'signalEventDefinition': 'signal',
    'errorEventDefinition': 'error',
    'terminateEventDefinition': 'terminate',
    'escalationEventDefinition': 'escalation',
    'compensateEventDefinition': 'compensate',
    'conditionalEventDefinition': 'conditional',
    'linkEventDefinition': 'link',
}

def _local_tag(elem) -> str:
    return elem.tag.split('}')[-1]

def _detect_event_type(elem) -> str:
    for child in elem:
        t = _local_tag(child)
        if t in EVENT_DEF_MAP:
            return ' ' + EVENT_DEF_MAP[t]
    return ''

def _detect_loop_type(elem) -> str:
    for child in elem:
        t = _local_tag(child)
        if t == 'standardLoopCharacteristics':
            return ' loop'
        elif t == 'multiInstanceLoopCharacteristics':
            if child.attrib.get('isSequential') == 'true':
                return ' loop sequential'
            return ' loop parallel'
    return ''

def decompile_bpmn_xml(bpmn_xml: str) -> str:
    """
    Decompiles BPMN 2.0 XML back into BPMN-as-Code DSL.
    Extracts process name, pools, swimlanes, events, tasks, gateways,
    subprocesses, sequence flows (including conditions and default flows),
    and message flows.
    """
    if not bpmn_xml or not bpmn_xml.strip():
        return ""

    try:
        root = ET.fromstring(bpmn_xml.strip())
    except Exception as exc:
        return f"# Ошибка парсинга BPMN XML: {exc}\n"

    # Find <process>
    process_elem = None
    for elem in root.iter():
        if _local_tag(elem) == 'process':
            process_elem = elem
            break

    if process_elem is None:
        return "# BPMN процесс не найден в XML\n"

    process_name = process_elem.attrib.get('name') or 'Бизнес-процесс'
    process_id = process_elem.attrib.get('id') or 'Process_1'

    # Collaboration, Pools & Message Flows
    pool_lines = []
    message_flow_lines = []
    main_pool_id = ''

    for collab in root.iter():
        if _local_tag(collab) == 'collaboration':
            for child in collab:
                ctag = _local_tag(child)
                if ctag == 'participant':
                    pid = child.attrib.get('id', '')
                    if not pid:
                        continue
                    pname = (child.attrib.get('name') or pid).replace('\n', ' ').strip()
                    pref = child.attrib.get('processRef', '')
                    if pref == process_id or (not main_pool_id and pref):
                        main_pool_id = pid
                    pool_lines.append(f'pool: {pid} "{pname}"')
                elif ctag == 'messageFlow':
                    msrc = child.attrib.get('sourceRef', '')
                    mtgt = child.attrib.get('targetRef', '')
                    mname = (child.attrib.get('name') or '').replace('\n', ' ').strip()
                    if msrc and mtgt:
                        if mname:
                            message_flow_lines.append(f'{msrc} ~> {mtgt} "{mname}"')
                        else:
                            message_flow_lines.append(f'{msrc} ~> {mtgt}')

    # Lanes & Node-to-lane mapping
    lane_lines = []
    node_to_lane = {}

    for elem in process_elem.iter():
        if _local_tag(elem) == 'laneSet':
            for lane in elem:
                if _local_tag(lane) == 'lane':
                    lid = lane.attrib.get('id', '')
                    if not lid:
                        continue
                    lname = (lane.attrib.get('name') or lid).replace('\n', ' ').strip()
                    pref = f" in {main_pool_id}" if main_pool_id else ""
                    lane_lines.append(f'lane: {lid} "{lname}"{pref}')
                    for child in lane:
                        if _local_tag(child) == 'flowNodeRef':
                            ref_id = (child.text or '').strip()
                            if ref_id:
                                node_to_lane[ref_id] = lid

    # Default flows
    default_flow_ids = set()
    for child in process_elem:
        def_attr = child.attrib.get('default')
        if def_attr:
            default_flow_ids.add(def_attr)

    buckets = {
        'start': [], 'end': [], 'catch_throw': [], 'boundary': [],
        'task': [], 'gateway': [], 'subprocess': [], 'call': []
    }
    flow_lines = []

    for child in process_elem:
        tag = _local_tag(child)
        cid = child.attrib.get('id', '')
        if not cid:
            continue
        cname = (child.attrib.get('name') or cid).replace('\n', ' ').strip()
        lane_mod = f" in {node_to_lane[cid]}" if cid in node_to_lane else ""
        loop_mod = _detect_loop_type(child)

        if tag == 'startEvent':
            ev_mod = _detect_event_type(child)
            buckets['start'].append(f'start: {cid} "{cname}"{ev_mod}{lane_mod}')
        elif tag == 'endEvent':
            ev_mod = _detect_event_type(child)
            buckets['end'].append(f'end: {cid} "{cname}"{ev_mod}{lane_mod}')
        elif tag == 'intermediateCatchEvent':
            ev_mod = _detect_event_type(child)
            buckets['catch_throw'].append(f'catch: {cid} "{cname}"{ev_mod}{lane_mod}')
        elif tag == 'intermediateThrowEvent':
            ev_mod = _detect_event_type(child)
            buckets['catch_throw'].append(f'throw: {cid} "{cname}"{ev_mod}{lane_mod}')
        elif tag == 'boundaryEvent':
            ev_mod = _detect_event_type(child)
            attached = child.attrib.get('attachedToRef', '')
            non_int = " non-interrupting" if child.attrib.get('cancelActivity') == 'false' else ""
            buckets['boundary'].append(f'boundary: {cid} on {attached} "{cname}"{ev_mod}{non_int}')
        elif tag in TASK_TAGS:
            task_type = f" {TASK_TYPE_MAP[tag]}" if tag in TASK_TYPE_MAP else ""
            performer = ""
            for doc in child:
                if _local_tag(doc) == 'documentation' and doc.text:
                    performer = doc.text.strip()
                    break
            by_mod = f' by "{performer}"' if (performer and cid not in node_to_lane) else ""
            buckets['task'].append(f'task: {cid} "{cname}"{task_type}{loop_mod}{by_mod}{lane_mod}')
        elif tag in GATEWAY_TAG_MAP:
            gw_type = GATEWAY_TAG_MAP[tag]
            buckets['gateway'].append(f'gateway: {cid} "{cname}" {gw_type}{lane_mod}')
        elif tag == 'subProcess':
            buckets['subprocess'].append(f'subprocess: {cid} "{cname}"{loop_mod}{lane_mod}')
        elif tag == 'callActivity':
            buckets['call'].append(f'call: {cid} "{cname}"{lane_mod}')
        elif tag == 'sequenceFlow':
            source = child.attrib.get('sourceRef', '')
            target = child.attrib.get('targetRef', '')
            is_def = cid in default_flow_ids
            flow_name = child.attrib.get('name', '').strip()
            if not flow_name:
                for cond in child:
                    if _local_tag(cond) == 'conditionExpression' and cond.text:
                        flow_name = cond.text.strip()
                        break
            if source and target:
                if is_def:
                    flow_lines.append(f'{source} ==> {target}')
                elif flow_name:
                    flow_lines.append(f'{source} --[{flow_name}]--> {target}')
                else:
                    flow_lines.append(f'{source} -> {target}')

    lines = [f'process "{process_name}"', '']

    def add_section(title, items):
        if items:
            lines.append(f'# {title}')
            lines.extend(items)
            lines.append('')

    if pool_lines or lane_lines:
        add_section('Пулы и дорожки', pool_lines + lane_lines)
    add_section('События', buckets['start'] + buckets['catch_throw'] + buckets['boundary'] + buckets['end'])
    add_section('Задачи', buckets['task'])
    add_section('Шлюзы', buckets['gateway'])
    add_section('Подпроцессы', buckets['subprocess'] + buckets['call'])
    add_section('Потоки управления', flow_lines)
    if message_flow_lines:
        add_section('Потоки сообщений', message_flow_lines)

    return '\n'.join(lines).strip() + '\n'

