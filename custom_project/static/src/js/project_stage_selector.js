/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { KanbanColumnQuickCreate } from "@web/views/kanban/kanban_column_quick_create";
import { useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

const TASK_TYPE_MODEL = "project.task.type";

patch(KanbanColumnQuickCreate.prototype, {
    setup() {
        super.setup();

        const relation = this.props.groupByField?.relation;
        this.isTaskTypeGroup = relation === TASK_TYPE_MODEL;

        // Always initialise — OWL resolves reactive state references at
        // setup time regardless of t-if branches. Leaving it undefined
        // when isTaskTypeGroup=false causes crashes in other kanbans.
        this.stageDropdown = useState({ stages: [], selectedId: "" });

        if (!this.isTaskTypeGroup) return;

        this.orm = useService("orm");

        onWillStart(async () => {
            const rows = await this.orm.searchRead(
                TASK_TYPE_MODEL,
                [],
                ["id", "name"],
                { order: "sequence asc" }
            );
            this.stageDropdown.stages = rows;
        });
    },

    /** Auto-submit as soon as the user picks a stage from the dropdown. */
    async onStageSelect(ev) {
        this.stageDropdown.selectedId = ev.target.value;
        await this.validate();
    },

    /**
     * Override `validate` — the method Odoo 19 calls both from the
     * "Add" button (t-on-click="validate") and from onInputKeydown (Enter).
     *
     * When isTaskTypeGroup: read from our select and call props.onValidate
     * directly (which is props.list.createGroup in the kanban renderer).
     * Otherwise: fall through to the original implementation unchanged.
     */
    async validate() {
        if (!this.isTaskTypeGroup) {
            return super.validate(...arguments);
        }

        const selectedId = parseInt(this.stageDropdown.selectedId, 10);
        if (!selectedId) return;

        const stage = this.stageDropdown.stages.find((s) => s.id === selectedId);
        if (!stage) return;

        if (this.props.onValidate) {
            await this.props.onValidate(stage.name);
        }
        this.stageDropdown.selectedId = "";
    },
});