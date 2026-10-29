"""Account lockout tracking scoped to the Django administration site."""

from axes.handlers.database import AxesDatabaseHandler


class AdminAxesDatabaseHandler(AxesDatabaseHandler):
    """Keep authentication outside the admin from recording or resetting attempts."""

    def user_login_failed(self, sender, credentials, request=None, **kwargs):
        if self.is_admin_request(request):
            return super().user_login_failed(sender, credentials, request, **kwargs)
        return None

    def user_logged_in(self, sender, request, user, **kwargs):
        if self.is_admin_request(request):
            return super().user_logged_in(sender, request, user, **kwargs)
        return None

    def user_logged_out(self, sender, request, user, **kwargs):
        if self.is_admin_request(request):
            return super().user_logged_out(sender, request, user, **kwargs)
        return None
