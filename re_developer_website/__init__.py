# -*- coding: utf-8 -*-
from . import models
from . import controllers


def post_init_hook(env):
    """Make the developer landing page the website homepage."""
    env['website'].search([]).write({'homepage_url': '/estate'})


def uninstall_hook(env):
    env['website'].search([('homepage_url', '=', '/estate')]).write({'homepage_url': False})
