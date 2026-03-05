"""Active Directory / LDAP authentication service.

NOTE: The ldap3 library is entirely synchronous.  All LDAP I/O is
offloaded to a thread via ``asyncio.to_thread`` so that a slow or
unresponsive AD server does not block the FastAPI event loop (and
therefore all other concurrent requests).
"""

import asyncio
import logging
from dataclasses import dataclass

from ldap3 import ALL, Connection, Server, SUBTREE
from ldap3.core.exceptions import LDAPException

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ADUser:
    """Represents a user retrieved from Active Directory."""

    username: str
    display_name: str
    email: str
    dn: str
    groups: list[str]  # List of group CNs the user belongs to


class ADAuthService:
    """Service for authenticating users against Active Directory via LDAP."""

    def __init__(self) -> None:
        self._server = Server(settings.ad_ldap_url, get_info=ALL)

    def _get_bind_connection(self) -> Connection:
        """Create a connection using the service account bind credentials."""
        conn = Connection(
            self._server,
            user=settings.ad_bind_dn,
            password=settings.ad_bind_password,
            auto_bind=True,
            read_only=True,
        )
        return conn

    def authenticate(self, username: str, password: str) -> ADUser | None:
        """Authenticate a user against AD and return their info if successful.

        Steps:
        1. Bind with service account to find the user's DN.
        2. Attempt to bind with the user's DN and password.
        3. If successful, retrieve user attributes and group memberships.
        """
        try:
            # Step 1: Find user DN using service account
            bind_conn = self._get_bind_connection()
            user_dn = self._find_user_dn(bind_conn, username)
            if not user_dn:
                logger.warning("AD auth: user '%s' not found in directory", username)
                bind_conn.unbind()
                return None

            bind_conn.unbind()

            # Step 2: Authenticate with user's credentials
            user_conn = Connection(
                self._server,
                user=user_dn,
                password=password,
                auto_bind=True,
                read_only=True,
            )

            # Step 3: Retrieve user attributes
            ad_user = self._get_user_info(user_conn, user_dn, username)
            user_conn.unbind()

            logger.info("AD auth: user '%s' authenticated successfully", username)
            return ad_user

        except LDAPException as e:
            logger.error("AD auth failed for user '%s': %s", username, str(e))
            return None

    async def authenticate_async(self, username: str, password: str) -> ADUser | None:
        """Async wrapper around :meth:`authenticate`.

        Offloads the blocking LDAP I/O to a worker thread so the event
        loop stays responsive.
        """
        return await asyncio.to_thread(self.authenticate, username, password)

    def _find_user_dn(self, conn: Connection, username: str) -> str | None:
        """Search for a user's DN by sAMAccountName."""
        search_base = settings.user_search_base
        search_filter = f"(sAMAccountName={username})"

        conn.search(
            search_base=search_base,
            search_filter=search_filter,
            search_scope=SUBTREE,
            attributes=["distinguishedName"],
        )

        if conn.entries:
            return str(conn.entries[0].distinguishedName)
        return None

    def _get_user_info(self, conn: Connection, user_dn: str, username: str) -> ADUser:
        """Retrieve user attributes and group memberships."""
        search_base = settings.user_search_base

        # Get user attributes
        conn.search(
            search_base=search_base,
            search_filter=f"(distinguishedName={user_dn})",
            search_scope=SUBTREE,
            attributes=["displayName", "mail", "memberOf", "sAMAccountName"],
        )

        if not conn.entries:
            raise LDAPException(f"Could not retrieve info for user DN: {user_dn}")

        entry = conn.entries[0]
        display_name = str(entry.displayName) if hasattr(entry, "displayName") else username
        email = str(entry.mail) if hasattr(entry, "mail") else ""
        member_of = entry.memberOf.values if hasattr(entry, "memberOf") else []

        # Extract group CNs from memberOf DNs
        groups = []
        for group_dn in member_of:
            cn = self._extract_cn(str(group_dn))
            if cn:
                groups.append(cn)

        return ADUser(
            username=username,
            display_name=display_name,
            email=email,
            dn=user_dn,
            groups=groups,
        )

    def _get_user_groups(self, conn: Connection, user_dn: str) -> list[str]:
        """Get all groups a user belongs to (including nested groups)."""
        search_base = settings.group_search_base
        search_filter = f"(member:1.2.840.113556.1.4.1941:={user_dn})"

        conn.search(
            search_base=search_base,
            search_filter=search_filter,
            search_scope=SUBTREE,
            attributes=["cn"],
        )

        return [str(entry.cn) for entry in conn.entries]

    @staticmethod
    def _extract_cn(dn: str) -> str | None:
        """Extract the CN from a distinguished name."""
        for part in dn.split(","):
            part = part.strip()
            if part.upper().startswith("CN="):
                return part[3:]
        return None


# Singleton instance
ad_auth_service = ADAuthService()
