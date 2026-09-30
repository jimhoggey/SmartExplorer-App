"""Single source of the app version (read by the app, the build spec and CI).
A release is a tag vX.Y.Z matching this; CI refuses to publish if they differ."""

APP_VERSION = "0.3.0"
