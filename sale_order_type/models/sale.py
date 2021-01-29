# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
# Copyright 2020 Tecnativa - Pedro M. Baeza
# Copyright 2021 Therp BV <https://therp.nl>.
# Copyright 2021 Sunflower IT < https://sunflowerweb.nl>.

from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    type_id = fields.Many2one(
        comodel_name="sale.order.type",
        string="Type",
        compute="_compute_sale_type_id",
        store=True,
        readonly=False,
        states={
            "sale": [("readonly", True)],
            "done": [("readonly", True)],
            "cancel": [("readonly", True)],
        },
        default=lambda so: so._default_type_id(),
        ondelete="restrict",
        copy=True,
    )

    @api.model
    def _default_type_id(self):
        return self.env["sale.order.type"].search([], limit=1)

    @api.depends("partner_id", "company_id")
    def _compute_sale_type_id(self):
        for record in self:
            if not record.partner_id:
                record.type_id = self.env["sale.order.type"].search(
                    [("company_id", "in", [self.env.company.id, False])], limit=1
                )
            else:
                sale_type = (
                    record.partner_id.with_context(
                        force_company=record.company_id.id
                    ).sale_type
                    or record.partner_id.commercial_partner_id.with_context(
                        force_company=record.company_id.id
                    ).sale_type
                )
                if sale_type:
                    record.type_id = sale_type

    @api.onchange("type_id")
    def onchange_type_id(self):
        # TODO: To be changed to computed stored readonly=False if possible in v14?
        vals = {}
        for order in self:
            order_type = order.type_id
            # Order values
            vals = {}
            if order_type.warehouse_id:
                vals.update({"warehouse_id": order_type.warehouse_id})
            if order_type.picking_policy:
                vals.update({"picking_policy": order_type.picking_policy})
            if order_type.payment_term_id:
                vals.update({"payment_term_id": order_type.payment_term_id})
            if order_type.pricelist_id:
                vals.update({"pricelist_id": order_type.pricelist_id})
            if order_type.incoterm_id:
                vals.update({"incoterm": order_type.incoterm_id})
            if vals:
                order.update(vals)
            # Order line values
            line_vals = {}
            line_vals.update({"route_id": order_type.route_id.id})
            order.order_line.update(line_vals)

    @api.model
    def create(self, vals):
        if vals.get("name", "/") == "/" and vals.get("type_id"):
            next_sequence = self._get_next_sequence(vals["type_id"])
            if next_sequence:
                vals["name"] = next_sequence
        return super(SaleOrder, self).create(vals)

    def write(self, vals):
        """ Maintain proper sequencing when copying """
        type_id = vals.get("type_id")
        if not type_id:
            return super(SaleOrder, self).write(vals)
        # Store orders that type_id has changed
        updated_orders = self.env["sale.order"]
        for this in self:
            # type_id remains the same.
            if this.type_id.id == type_id:
                continue
            next_sequence = self._get_next_sequence(type_id)
            # No next sequence for this type_id
            if not next_sequence:
                continue
            # Change the name
            new_vals = vals.copy()
            new_vals["name"] = next_sequence
            super(SaleOrder, this).write(new_vals)
            updated_orders += this
        return super(SaleOrder, self - updated_orders).write(vals)

    def _prepare_invoice(self):
        res = super(SaleOrder, self)._prepare_invoice()
        if self.type_id.journal_id:
            res["journal_id"] = self.type_id.journal_id.id
        if self.type_id:
            res["sale_type_id"] = self.type_id.id
        return res

    def _get_next_sequence(self, type_id):
        sale_type = self.env["sale.order.type"].browse(type_id)
        sequence = False
        if sale_type.sequence_id:
            sequence = sale_type.sequence_id.next_by_id()
        return sequence


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    @api.onchange("product_id")
    def product_id_change(self):
        res = super(SaleOrderLine, self).product_id_change()
        if self.order_id.type_id.route_id:
            self.update({"route_id": self.order_id.type_id.route_id})
        return res
