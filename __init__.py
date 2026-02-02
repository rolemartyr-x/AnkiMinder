"""Anki entrypoint for the Beeminder integration add-on."""

from .anki_beeminder.addon import initialize_addon

initialize_addon(__name__)

