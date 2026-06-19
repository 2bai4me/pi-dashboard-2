def _generate_bpmn(sop: SOP) -> str:
    """Generiert valides BPMN 2.0 XML aus einer SOP-Definition (bpmn-js-kompatibel).

    Architektur (User-Direktive 17.06.2026):
    - Top-Level: 4 SubProcesses (kollabierbar) + Start/End in horizontalem Layout
        1. Ziel-Erfassung (User-Input-Schritte)
        2. Spec-Generierung (Orchestrator + Subagenten)
        3. CIO Review-Zirkel (Reviews + Gateways + Loop-Back)
        4. Spec-Finalizer
    - SubProcesses sind collapsed: isExpanded=false (bpmn-js zeigt + zum Aufklappen)
    - Innerhalb jedes SubProcess: alle Steps + Gateways + Edges
    - Loop-Back-Edge: vom Review-SubProcess zurueck zum Spec-Generierung-SubProcess
      (sichtbar als horizontaler Bogen unter den SubProcesses)
    - Beim Klick auf einen SubProcess expandiert bpmn-js ihn automatisch
    - Grosszuegige Abstaende zwischen den Elementen
    """
    ns = "http://www.omg.org/spec/BPMN/20100524/MODEL"
    bpmndi_ns = "http://www.omg.org/spec/BPMN/20100524/DI"
    dc_ns = "http://www.omg.org/spec/DD/20100524/DC"
    di_ns = "http://www.omg.org/spec/DD/20100524/DI"
    bpmnjs_ns = "http://bpmn.io/schema/bpmn-js"

    defs_id = f"Definitions_{sop.id}"
    proc_id = f"Process_{sop.id}"
    start_id = f"start_{sop.id}"
    end_id = f"end_{sop.id}"

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<bpmn:definitions xmlns:bpmn="{ns}" '
        f'xmlns:bpmndi="{bpmndi_ns}" '
        f'xmlns:dc="{dc_ns}" '
        f'xmlns:di="{di_ns}" '
        f'xmlns:bpmnjs="{bpmnjs_ns}" '
        f'id="{defs_id}" targetNamespace="http://bpmn.io/schema/bpmn">',
        f'  <bpmn:process id="{proc_id}" name="{_xml_escape(sop.name)}" isExecutable="false">',
        f'    <bpmn:documentation>{_xml_escape(sop.description or "")}</bpmn:documentation>',
    ]

    sorted_steps = sorted(sop.steps, key=lambda s: s.step_order)
    if not sorted_steps:
        parts.append(f'    <bpmn:startEvent id="{start_id}" name="SOP Start" />')
        parts.append(f'    <bpmn:endEvent id="{end_id}" name="SOP End" />')
        parts.append(f'    <bpmn:sequenceFlow id="flow_empty" sourceRef="{start_id}" targetRef="{end_id}" />')
        parts.append('  </bpmn:process>')
        parts.append('</bpmn:definitions>')
        return "\n".join(parts)

    # === Schritte in SubProcess-Gruppen klassifizieren ===
    def _classify(step) -> str:
        if step.phase == "End":
            return "finalizer"
        if step.rules:
            return "review"
        if step.input_tool_required or (step.agent and "ceo" in step.agent.lower()):
            return "input"
        if step.agent and step.agent.startswith("pi-coder-spec"):
            return "subagent"
        if step.agent and step.agent.startswith("pi-coder"):
            return "orchestrator"
        return "other"

    groups: dict = {"input": [], "orchestrator": [], "subagent": [], "review": [], "finalizer": [], "other": []}
    for s in sorted_steps:
        groups[_classify(s)].append(s)

    sp_defs = []
    if groups["input"]:
        sp_defs.append({"id": "sp1_input", "name": "1. Ziel-Erfassung", "steps": groups["input"]})
    if groups["orchestrator"] or groups["subagent"]:
        all_gen = groups["orchestrator"] + groups["subagent"]
        sp_defs.append({"id": "sp2_gen", "name": "2. Spec-Generierung (Schwarm)", "steps": all_gen})
    if groups["review"]:
        sp_defs.append({"id": "sp3_review", "name": "3. CIO Review-Zirkel", "steps": groups["review"]})
    if groups["finalizer"]:
        sp_defs.append({"id": "sp4_final", "name": "4. Spec-Finalizer", "steps": groups["finalizer"]})

    # === Top-Level: StartEvent + SubProcesses + EndEvent ===
    parts.append(f'    <bpmn:startEvent id="{start_id}" name="SOP Start" />')

    for sp in sp_defs:
        parts.append(f'    <bpmn:subProcess id="{sp["id"]}" name="{_xml_escape(sp["name"])}">')
        sp_steps = sp["steps"]
        step_gw: dict = {}

        # Tasks + Gateways
        for step in sp_steps:
            if step.agent and step.agent.startswith("pi-coder-spec"):
                task_tag = "bpmn:scriptTask"
            elif step.agent and step.agent.startswith("pi-coder"):
                task_tag = "bpmn:scriptTask"
            elif step.agent in ("user", "CEO", "CEO-digital"):
                task_tag = "bpmn:userTask"
            elif step.phase == "End":
                task_tag = "bpmn:serviceTask"
            else:
                task_tag = "bpmn:serviceTask"
            doc_text = (
                f"Phase: {step.phase} | Agent: {step.agent} | "
                f"Trigger: {step.trigger} | Action: {step.action} | "
                f"Expected: {(step.expected_result or '')[:80]} | Delay: {step.delay_s}s"
            )
            parts.append(
                f'      <{task_tag} id="step_{step.id}" name="{_xml_escape(step.name)}">'
                f'<bpmn:documentation>{_xml_escape(doc_text)}</bpmn:documentation>'
                f'</{task_tag}>'
            )
            if step.rules:
                gw_id = f"gw_{step.id}"
                step_gw[step.id] = gw_id
                parts.append(f'      <bpmn:exclusiveGateway id="{gw_id}" name="?" />')

        # Inner-SubProcess-Edges
        for i, step in enumerate(sp_steps):
            if step.id in step_gw:
                gw = step_gw[step.id]
                # Step -> Gateway
                parts.append(
                    f'      <bpmn:sequenceFlow id="inner_step_{step.id}_to_gw" '
                    f'sourceRef="step_{step.id}" targetRef="{gw}" />'
                )
                # Rule-Conditional-Flows
                for ridx, rule in enumerate(sorted(step.rules, key=lambda r: r.rule_order)):
                    tgt = rule.action_target
                    if tgt in [s.id for s in sp_steps]:
                        target_ref = f"step_{tgt}"
                    elif tgt and tgt in [s.id for s in sorted_steps]:
                        # Loop-Back: zeigt auf Step in einem anderen (collapsed) SubProcess
                        target_ref = f"step_{tgt}"
                    else:
                        target_ref = end_id
                    cond_text = f"{rule.condition_field} {rule.condition_operator} {rule.condition_value}"
                    parts.append(
                        f'      <bpmn:sequenceFlow id="inner_gw_{step.id}_r{ridx}" '
                        f'sourceRef="{gw}" targetRef="{target_ref}">'
                        f'<bpmn:conditionExpression>{_xml_escape(cond_text)}</bpmn:conditionExpression>'
                        f'</bpmn:sequenceFlow>'
                    )
                # Default-Flow
                default_target = step.next_step_id
                if default_target and default_target in [s.id for s in sp_steps]:
                    default_ref = f"step_{default_target}"
                else:
                    default_ref = end_id
                parts.append(
                    f'      <bpmn:sequenceFlow id="inner_gw_{step.id}_default" '
                    f'sourceRef="{gw}" targetRef="{default_ref}" name="default" />'
                )
            else:
                if i + 1 < len(sp_steps):
                    next_s = sp_steps[i + 1]
                    parts.append(
                        f'      <bpmn:sequenceFlow id="inner_step_{step.id}" '
                        f'sourceRef="step_{step.id}" targetRef="step_{next_s.id}" '
                        f'name="{_xml_escape(_flow_label(step))}" />'
                    )
        parts.append('    </bpmn:subProcess>')

    parts.append(f'    <bpmn:endEvent id="{end_id}" name="SOP End" />')

    # === Top-Level-Edges ===
    if sp_defs:
        parts.append(
            f'    <bpmn:sequenceFlow id="flow_start_to_sp1" '
            f'sourceRef="{start_id}" targetRef="{sp_defs[0]["id"]}" name="start" />'
        )
        for i in range(len(sp_defs) - 1):
            parts.append(
                f'    <bpmn:sequenceFlow id="flow_sp{i+1}_to_sp{i+2}" '
                f'sourceRef="{sp_defs[i]["id"]}" targetRef="{sp_defs[i + 1]["id"]}" />'
            )
        parts.append(
            f'    <bpmn:sequenceFlow id="flow_sp_last_to_end" '
            f'sourceRef="{sp_defs[-1]["id"]}" targetRef="{end_id}" />'
        )

    parts.append('  </bpmn:process>')

    # === BPMN-DI (Diagram Interchange) ===
    # Layout: horizontal, grosszuegige Abstaende
    SP_W = 240
    SP_H = 110
    X_START = 80
    Y_CENTER = 280
    SP_GAP = 240  # horizontaler Abstand

    parts.append(f'  <bpmndi:BPMNDiagram id="BPMNDiagram_{sop.id}">')
    parts.append(f'    <bpmndi:BPMNPlane id="BPMNPlane_{sop.id}" bpmnElement="{proc_id}">')

    def _shape_bounds(elem_id: str, x: int, y: int, w: int, h: int) -> str:
        return (
            f'      <bpmndi:BPMNShape id="{elem_id}_di" bpmnElement="{elem_id}">\n'
            f'        <dc:Bounds x="{x}" y="{y}" width="{w}" height="{h}" />\n'
            f'      </bpmndi:BPMNShape>'
        )

    def _shape_subprocess(elem_id: str, x: int, y: int, w: int, h: int) -> str:
        return (
            f'      <bpmndi:BPMNShape id="{elem_id}_di" bpmnElement="{elem_id}">\n'
            f'        <dc:Bounds x="{x}" y="{y}" width="{w}" height="{h}" />\n'
            f'        <bpmndi:BPMNLabel/>\n'
            f'        <bpmnjs:isExpanded>false</bpmnjs:isExpanded>\n'
            f'      </bpmndi:BPMNShape>'
        )

    # StartEvent
    parts.append(_shape_bounds(start_id, X_START, Y_CENTER - 25, 50, 50))
    # SubProcesses
    x_cursor = X_START + 50 + 180
    sp_x: dict = {}
    for sp in sp_defs:
        sp_x[sp["id"]] = x_cursor
        parts.append(_shape_subprocess(sp["id"], x_cursor, Y_CENTER - SP_H // 2, SP_W, SP_H))
        x_cursor += SP_W + SP_GAP
    # EndEvent
    x_end = x_cursor
    parts.append(_shape_bounds(end_id, x_end, Y_CENTER - 25, 50, 50))

    # === Top-Level-Edges (waypoints) ===
    def _edge_h(eid: str, src: str, tgt: str, src_x: int, tgt_x: int, y: int) -> str:
        return (
            f'      <bpmndi:BPMNEdge id="{eid}_di" bpmnElement="{eid}">\n'
            f'        <di:waypoint x="{src_x}" y="{y}" />\n'
            f'        <di:waypoint x="{tgt_x}" y="{y}" />\n'
            f'      </bpmndi:BPMNEdge>'
        )

    if sp_defs:
        sp0 = sp_defs[0]
        parts.append(_edge_h("flow_start_to_sp1", start_id, sp0["id"],
                              X_START + 50, sp_x[sp0["id"]], Y_CENTER))
        for i in range(len(sp_defs) - 1):
            src_sp = sp_defs[i]
            tgt_sp = sp_defs[i + 1]
            parts.append(_edge_h(
                f"flow_sp{i+1}_to_sp{i+2}", src_sp["id"], tgt_sp["id"],
                sp_x[src_sp["id"]] + SP_W, sp_x[tgt_sp["id"]], Y_CENTER
            ))
        last_sp = sp_defs[-1]
        parts.append(_edge_h(
            "flow_sp_last_to_end", last_sp["id"], end_id,
            sp_x[last_sp["id"]] + SP_W, x_end, Y_CENTER
        ))

    parts.append('    </bpmndi:BPMNPlane>')
    parts.append('  </bpmndi:BPMNDiagram>')
    parts.append('</bpmn:definitions>')
    return "\n".join(parts)
