"""Anki entrypoint for the Beeminder integration add-on."""

from .ankiminder.addon import initialize_addon

initialize_addon(__name__)

