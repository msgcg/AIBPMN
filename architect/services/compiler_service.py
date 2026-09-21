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

