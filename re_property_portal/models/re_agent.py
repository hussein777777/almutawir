# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import email_normalize

from odoo.addons.re_developer_website.models.tools import whatsapp_url

_logger = logging.getLogger(__name__)


class ReAgent(models.Model):
    """A person who publishes listings: an agent of an agency or an individual owner.
    Active agents get a portal account to manage their own listings."""
    _name = 're.agent'
    _description = 'Real Estate Agent'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'image.mixin',
                'website.published.mixin', 'website.seo.metadata']
    _order = 'is_verified desc, name'

    name = fields.Char(required=True, tracking=True)
    agent_kind = fields.Selection([
        ('agent', 'Agent / Broker'),
        ('owner', 'Property Owner'),
    ], string='Type', required=True, default='agent', tracking=True)
    state = fields.Selection([
        ('pending', 'Pending Approval'),
        ('active', 'Active'),
        ('blocked', 'Blocked'),
    ], default='pending', required=True, tracking=True, index=True)
    is_verified = fields.Boolean('Verified', tracking=True)
    active = fields.Boolean(default=True)
    agency_id = fields.Many2one('re.agency', 'Agency', index=True, tracking=True)
    requested_agency = fields.Char('Agency (as requested)', help='Agency name typed in the sign-up request.')
    job_title = fields.Char(translate=True)
    phone = fields.Char(required=True)
    whatsapp = fields.Char('WhatsApp')
    whatsapp_url = fields.Char(compute='_compute_whatsapp_url')
    email = fields.Char(required=True)
    languages = fields.Char(help='e.g. Arabic, English')
    bio = fields.Text(translate=True)
    partner_id = fields.Many2one('res.partner', 'Contact', ondelete='restrict', copy=False)
    user_id = fields.Many2one('res.users', 'Portal User', ondelete='set null', copy=False, index=True)
    listing_ids = fields.One2many('re.listing', 'agent_id', 'Listings')
    listing_count = fields.Integer('Published Listings', compute='_compute_listing_count')
    lead_count = fields.Integer(compute='_compute_lead_count')

    _sql_constraints = [
        ('user_uniq', 'unique(user_id)', 'This user is already linked to another agent.'),
    ]

    @api.depends('whatsapp', 'phone')
    def _compute_whatsapp_url(self):
        for agent in self:
            agent.whatsapp_url = whatsapp_url(agent.whatsapp or agent.phone)

    def _compute_listing_count(self):
        Listing = self.env['re.listing'].sudo()
        for agent in self:
            agent.listing_count = Listing.search_count([('agent_id', '=', agent.id), ('state', '=', 'published')])

    def _compute_lead_count(self):
        Lead = self.env['crm.lead'].sudo()
        for agent in self:
            agent.lead_count = Lead.search_count([('re_agent_id', '=', agent.id)])

    def _compute_website_url(self):
        super()._compute_website_url()
        for agent in self:
            if agent.id:
                agent.website_url = '/agent/%s' % self.env['ir.http']._slug(agent)

    @api.model
    def _get_for_user(self, user=None):
        """Active agent linked to the given (or current) user, as sudo record."""
        user = user or self.env.user
        if not user or user._is_public():
            return self.sudo().browse()
        return self.sudo().search([('user_id', '=', user.id), ('state', '=', 'active')], limit=1)

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------
    def _ensure_partner(self):
        for agent in self:
            if not agent.partner_id:
                agent.partner_id = self.env['res.partner'].sudo().create({
                    'name': agent.name,
                    'email': agent.email,
                    'phone': agent.phone,
                    'parent_id': False,
                    'image_1920': agent.image_1920,
                })

    def _ensure_portal_user(self):
        """Create a portal account and email the invitation (sign-up link)."""
        portal_group = self.env.ref('base.group_portal')
        for agent in self:
            if agent.user_id:
                if not agent.user_id.active:
                    agent.user_id.sudo().active = True
                continue
            login = email_normalize(agent.email)
            if not login:
                raise UserError(_('Agent %s needs a valid email to get a portal account.', agent.name))
            existing = self.env['res.users'].sudo().with_context(active_test=False).search(
                [('login', '=', login)], limit=1)
            if existing:
                if not existing.share:
                    raise UserError(_('%s is an internal user, link it manually if needed.', login))
                agent.user_id = existing
                existing.active = True
                continue
            agent._ensure_partner()
            user = self.env['res.users'].sudo().with_context(no_reset_password=True).create({
                'name': agent.name,
                'login': login,
                'email': login,
                'partner_id': agent.partner_id.id,
                'groups_id': [(6, 0, [portal_group.id])],
            })
            agent.user_id = user
            try:
                user.action_reset_password()
            except Exception:  # mail server not configured: account still works
                _logger.warning('Could not send the portal invitation to %s', login, exc_info=True)
                agent.message_post(body=_(
                    'The invitation email could not be sent. Check the outgoing mail server, '
                    'then click "Resend Invitation".'))

    def action_approve(self):
        for agent in self:
            agent._ensure_partner()
            agent._ensure_portal_user()
            agent.write({'state': 'active', 'is_published': True})
            agent.message_post(body=_('Agent approved and invited to the portal.'))

    def action_block(self):
        self.write({'state': 'blocked', 'is_published': False})
        self.listing_ids.filtered(lambda l: l.state in ('published', 'pending')).write({
            'state': 'draft', 'is_published': False})
        self.user_id.sudo().write({'active': False})

    def action_resend_invitation(self):
        for agent in self.filtered('user_id'):
            agent.user_id.sudo().action_reset_password()

    def action_view_listings(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Listings'),
            'res_model': 're.listing',
            'view_mode': 'list,kanban,form',
            'domain': [('agent_id', '=', self.id)],
            'context': {'default_agent_id': self.id},
        }

    def action_view_leads(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Inquiries'),
            'res_model': 'crm.lead',
            'view_mode': 'list,form',
            'domain': [('re_agent_id', '=', self.id)],
        }
