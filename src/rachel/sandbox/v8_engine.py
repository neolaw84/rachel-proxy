import logging
import multiprocessing
import traceback
import json
from typing import Any
from rachel.sandbox.base import SandboxEngine

logger = logging.getLogger(__name__)

def _v8_worker(
    code: str,
    state: dict[str, Any],
    result_queue: multiprocessing.Queue,
) -> None:
    from py_mini_racer import MiniRacer

    # Redefine console.log to redirect prints to our logs buffer
    js_init = """
    var _logs = [];
    var console = {
        log: function() {
            var args = Array.prototype.slice.call(arguments);
            var msg = args.map(function(x) {
                if (x === null) return "null";
                if (x === undefined) return "undefined";
                if (typeof x === 'object') {
                    try { return JSON.stringify(x); } catch(e) { return String(x); }
                }
                return String(x);
            }).join(' ');
            _logs.push(msg);
        }
    };
    function roll_xdy(numDice, numSides, interpretation) {
        var rolls = [];
        var total = 0;
        for (var i = 0; i < numDice; i++) {
            var r = Math.floor(Math.random() * numSides) + 1;
            rolls.push(r);
            total += r;
        }
        var keys = [];
        if (interpretation && typeof interpretation === 'object') {
            for (var k in interpretation) {
                if (Object.prototype.hasOwnProperty.call(interpretation, k)) {
                    var numKey = Number(k);
                    if (!isNaN(numKey)) {
                        keys.push(numKey);
                    }
                }
            }
        }
        keys.sort(function(a, b) { return a - b; });
        var interp = "";
        for (var j = 0; j < keys.length; j++) {
            if (total <= keys[j]) {
                interp = interpretation[keys[j]] || interpretation[String(keys[j])];
                break;
            }
        }
        if (!interp && keys.length > 0) {
            var maxKey = keys[keys.length - 1];
            interp = interpretation[maxKey] || interpretation[String(maxKey)];
        }
        var interpStr = "interpretation of the dice roll is '" + interp + "'";
        console.log("Rolled " + numDice + "d" + numSides + ": [" + rolls.join(", ") + "] = " + total + "\\n" + interpStr);
        return {
            rolls: rolls,
            total: total,
            interpretation: interpStr
        };
    }
    function contest(p1_dice, p2_dice, m1, m2, interpretation) {
        var p1_rolls = [];
        var p1_total = 0;
        var p1_num = (p1_dice && typeof p1_dice.num === 'number') ? p1_dice.num : 1;
        var p1_sides = (p1_dice && typeof p1_dice.sides === 'number') ? p1_dice.sides : 6;
        for (var i = 0; i < p1_num; i++) {
            var r = Math.floor(Math.random() * p1_sides) + 1;
            p1_rolls.push(r);
            p1_total += r;
        }
        var p2_rolls = [];
        var p2_total = 0;
        var p2_num = (p2_dice && typeof p2_dice.num === 'number') ? p2_dice.num : 1;
        var p2_sides = (p2_dice && typeof p2_dice.sides === 'number') ? p2_dice.sides : 6;
        for (var i = 0; i < p2_num; i++) {
            var r = Math.floor(Math.random() * p2_sides) + 1;
            p2_rolls.push(r);
            p2_total += r;
        }
        var p1_mod = 0;
        var p1_mod_details = [];
        if (m1 && typeof m1 === 'object') {
            for (var k in m1) {
                if (Object.prototype.hasOwnProperty.call(m1, k)) {
                    var val = Number(m1[k]);
                    if (!isNaN(val)) {
                        p1_mod += val;
                        p1_mod_details.push(k + " (+" + val + ")");
                    }
                }
            }
        }
        var p2_mod = 0;
        var p2_mod_details = [];
        if (m2 && typeof m2 === 'object') {
            for (var k in m2) {
                if (Object.prototype.hasOwnProperty.call(m2, k)) {
                    var val = Number(m2[k]);
                    if (!isNaN(val)) {
                        p2_mod += val;
                        p2_mod_details.push(k + " (+" + val + ")");
                    }
                }
            }
        }
        var p1_final = p1_total + p1_mod;
        var p2_final = p2_total + p2_mod;
        var diff = p1_final - p2_final;
        var keys = [];
        if (interpretation && typeof interpretation === 'object') {
            for (var k in interpretation) {
                if (Object.prototype.hasOwnProperty.call(interpretation, k)) {
                    var numKey = Number(k);
                    if (!isNaN(numKey)) {
                        keys.push(numKey);
                    }
                }
            }
        }
        keys.sort(function(a, b) { return a - b; });
        var interp = "";
        for (var j = 0; j < keys.length; j++) {
            if (diff <= keys[j]) {
                interp = interpretation[keys[j]] || interpretation[String(keys[j])];
                break;
            }
        }
        if (!interp && keys.length > 0) {
            var maxKey = keys[keys.length - 1];
            interp = interpretation[maxKey] || interpretation[String(maxKey)];
        }
        var resultStr = "Contest results: " +
            "Party 1 rolled " + p1_num + "d" + p1_sides + ": [" + p1_rolls.join(", ") + "] (Total: " + p1_total + ") " +
            (p1_mod_details.length ? "with mods " + p1_mod_details.join(", ") + " " : "") + "= " + p1_final + ". " +
            "Party 2 rolled " + p2_num + "d" + p2_sides + ": [" + p2_rolls.join(", ") + "] (Total: " + p2_total + ") " +
            (p2_mod_details.length ? "with mods " + p2_mod_details.join(", ") + " " : "") + "= " + p2_final + ". " +
            "Difference: " + diff + ". Outcome: " + interp;
        console.log(resultStr);
        return {
            p1_total: p1_total,
            p1_final: p1_final,
            p2_total: p2_total,
            p2_final: p2_final,
            diff: diff,
            outcome: interp
        };
    }
    function update_plan_status(updates) {
        if (!plan || !Array.isArray(plan)) {
            console.log("No plan array found to update.");
            return;
        }
        var updated_count = 0;
        if (updates && Array.isArray(updates)) {
            for (var i = 0; i < updates.length; i++) {
                var u = updates[i];
                if (u && u.id !== undefined && u.status !== undefined) {
                    for (var j = 0; j < plan.length; j++) {
                        if (plan[j] && String(plan[j].id) === String(u.id)) {
                            plan[j].status = u.status;
                            updated_count++;
                        }
                    }
                }
            }
        }
        console.log("Updated status of " + updated_count + " plan items.");
        return "Updated status of " + updated_count + " plan items successfully";
    }
    """

    is_wrapper = isinstance(state, dict) and "state" in state and "hidden_state" in state

    if is_wrapper:
        state_json = json.dumps(state.get("state", {}), ensure_ascii=False)
        hidden_json = json.dumps(state.get("hidden_state", {}), ensure_ascii=False)
        plan_json = json.dumps(state.get("plan", []), ensure_ascii=False)
        js_init += f"\nvar state = {state_json};\nvar hidden_state = {hidden_json};\nvar plan = {plan_json};\n"
    else:
        state_json = json.dumps(state, ensure_ascii=False)
        js_init += f"\nvar state = {state_json};\n"

    # Wrap inside IIFE and catch execution exceptions
    if is_wrapper:
        js_run = f"""
        try {{
            (function() {{
                {code}
            }})();
        }} catch (e) {{
            _logs.push("--- Sandbox Exception ---");
            _logs.push(e.stack || e.toString());
        }}
        JSON.stringify({{state: state, hidden_state: hidden_state, plan: plan, logs: _logs}});
        """
    else:
        js_run = f"""
        try {{
            (function() {{
                {code}
            }})();
        }} catch (e) {{
            _logs.push("--- Sandbox Exception ---");
            _logs.push(e.stack || e.toString());
        }}
        JSON.stringify({{state: state, logs: _logs}});
        """

    try:
        ctx = MiniRacer()
        ctx.eval(js_init)
        result_str = ctx.eval(js_run)
        res = json.loads(result_str)
        if is_wrapper:
            updated_state = res.get("state", {})
            updated_hidden = res.get("hidden_state", {})
            updated_plan = res.get("plan", [])
            if not isinstance(updated_state, dict):
                logs = "\n".join(res.get("logs", [])) + (
                    "\n--- Sandbox Warning: 'state' was replaced with a non-object; "
                    "reverting to original state. ---\n"
                )
                updated_state = state.get("state", {})
            if not isinstance(updated_hidden, dict):
                logs = "\n".join(res.get("logs", [])) + (
                    "\n--- Sandbox Warning: 'hidden_state' was replaced with a non-object; "
                    "reverting to original hidden_state. ---\n"
                )
                updated_hidden = state.get("hidden_state", {})
            if not isinstance(updated_plan, list):
                logs = "\n".join(res.get("logs", [])) + (
                    "\n--- Sandbox Warning: 'plan' was replaced with a non-list; "
                    "reverting to original plan. ---\n"
                )
                updated_plan = state.get("plan", [])
            
            logs = "\n".join(res.get("logs", []))
            updated_wrapper = {
                "state": updated_state,
                "hidden_state": updated_hidden,
                "plan": updated_plan
            }
            result_queue.put((updated_wrapper, logs))
        else:
            updated_state = res.get("state", state)
            if not isinstance(updated_state, dict):
                logs = "\n".join(res.get("logs", [])) + (
                    "\n--- Sandbox Warning: 'state' was replaced with a non-object; "
                    "reverting to original state. ---\n"
                )
                updated_state = state
            else:
                logs = "\n".join(res.get("logs", []))
            result_queue.put((updated_state, logs))
    except Exception as exc:
        logs = f"--- Sandbox Exception ---\n{traceback.format_exc()}"
        result_queue.put((state, logs))

class V8SandboxEngine(SandboxEngine):
    """Execution engine for sandboxed JavaScript via V8 isolates."""

    @property
    def name(self) -> str:
        return "v8"

    def execute(
        self,
        code: str,
        state: dict[str, Any],
        timeout_seconds: float = 2.0,
    ) -> tuple[dict[str, Any], str]:
        ctx = multiprocessing.get_context("spawn")
        result_queue: multiprocessing.Queue = ctx.Queue()

        proc = ctx.Process(
            target=_v8_worker,
            args=(code, dict(state), result_queue),
            daemon=True,
        )
        proc.start()
        proc.join(timeout=timeout_seconds)

        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=2.0)
            if proc.is_alive():
                proc.kill()
            logger.warning("V8 sandbox timed out after %.1fs and was killed.", timeout_seconds)
            return state, f"[Sandbox timed out after {timeout_seconds}s — execution aborted]"

        if not result_queue.empty():
            updated_state, output = result_queue.get_nowait()
            return updated_state, output

        logger.error("V8 sandbox worker exited without producing a result (exit code %s).", proc.exitcode)
        return state, f"[Sandbox worker crashed unexpectedly (exit code {proc.exitcode})]"
