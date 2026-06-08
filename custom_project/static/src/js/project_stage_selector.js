/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { KanbanColumnQuickCreate } from "@web/views/kanban/kanban_column_quick_create";
import { useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

const TASK_TYPE_MODEL = "project.task.type";

/**
 * Patch KanbanColumnQuickCreate so that, when the kanban is grouped by
 * project.task.type (project task stages), the column quick-create widget
 * shows a <select> of existing stages instead of a free-text input.
 *
 * The patch works in three parts:
 *   1. setup()           – detect whether we're in a stage-grouped kanban,
 *                          load all configured stages via ORM.
 *   2. onStageSelect()   – keep track of which stage the user chose.
 *   3. validateQuickCreate() – pass the chosen stage name to the parent's
 *                          onValidate, which calls name_create on the server.
 *                          The model-level name_create override converts the
 *                          name lookup into an existing-record link rather
 *                          than a creation.
 *
 * The companion template override (project_stage_selector.xml) replaces
 * the <input> element with the <select> when isTaskTypeGroup is true.
 */
patch(KanbanColumnQuickCreate.prototype, {
    setup() {
        super.setup();

        const relation = this.props.groupByField?.relation;
        this.isTaskTypeGroup = relation === TASK_TYPE_MODEL;

        if (!this.isTaskTypeGroup) return;

        this.orm = useService("orm");
        this.stageDropdown = useState({
            stages: [],
            selectedId: "",
        });

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

    /** Called by the <select t-on-change> in the template override. */
    async onStageSelect(ev) {
        this.stageDropdown.selectedId = ev.target.value;
        // NEW: Auto-submit the moment the user selects an option
        await this.validateQuickCreate();
    },
    async validateQuickCreate() {
        if (!this.isTaskTypeGroup) {
            return super.validateQuickCreate(...arguments);
        }

        const selectedId = parseInt(this.stageDropdown.selectedId, 10);
        if (!selectedId) return;

        const stage = this.stageDropdown.stages.find((s) => s.id === selectedId);
        if (!stage) return;

        // props.onValidate(name) calls name_create on the server.
        // Our model override converts the name → existing record id.
        if (this.props.onValidate) {
            await this.props.onValidate(stage.name);
        }
        this.stageDropdown.selectedId = "";
    },
});