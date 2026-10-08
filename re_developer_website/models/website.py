# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .tools import video_embed_url, whatsapp_url


class Website(models.Model):
    _inherit = 'website'

    # Hero
    re_tagline = fields.Char('Hero Tagline', translate=True, default='Building Communities That Last')
    re_hero_subtitle = fields.Text('Hero Subtitle', translate=True)
    re_hero_image = fields.Image('Hero Image', max_width=1920, max_height=1080)

    # Company overview / interview
    re_overview_title = fields.Char('Overview Title', translate=True, default='Company Overview')
    re_overview = fields.Html('Company Overview', translate=True, sanitize_attributes=False)
    re_video_url = fields.Char('Company Interview / Overview Video', help='YouTube or Vimeo link.')
    re_video_embed_url = fields.Char(compute='_compute_re_links')
    re_vision = fields.Text('Vision', translate=True)
    re_mission = fields.Text('Mission', translate=True)

    # Key figures
    re_founded_year = fields.Integer('Founded In')
    re_years_experience = fields.Integer('Years of Experience')
    re_projects_count = fields.Integer('Projects Delivered')
    re_units_count = fields.Integer('Units Delivered')
    re_clients_count = fields.Integer('Happy Clients')

    # Contact
    re_whatsapp = fields.Char('WhatsApp Number')
    re_whatsapp_url = fields.Char(compute='_compute_re_links')
    re_office_hours = fields.Char('Office Hours', translate=True, default='Sat - Thu, 10:00 AM - 7:00 PM')

    # Lead routing
    re_lead_team_id = fields.Many2one('crm.team', 'Inquiries Sales Team')
    re_lead_user_id = fields.Many2one('res.users', 'Inquiries Salesperson', domain=[('share', '=', False)])

    @api.depends('re_video_url', 're_whatsapp')
    def _compute_re_links(self):
        for website in self:
            website.re_video_embed_url = video_embed_url(website.re_video_url)
            website.re_whatsapp_url = whatsapp_url(website.re_whatsapp)
