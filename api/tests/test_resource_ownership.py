import json
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services.resource_ownership import ownership_marker, require_owned, resource_hostname
from app.services.deploy_executor import _require_attempt_owned
from app.services.deploy_teardown import destroy_lxc_container, teardown_deploy_by_hostname, TeardownError
from app.services.proxmox_adapter import ProxmoxError


class OwnershipTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.ids = tuple(uuid.uuid4() for _ in range(4))
        self.adapter = SimpleNamespace(get_lxc_config=AsyncMock(), stop_lxc=AsyncMock(),
                                       destroy_lxc=AsyncMock(), wait_for_task=AsyncMock())
        self.adapter.get_lxc_config.return_value = {
            'description': ownership_marker(*self.ids)}

    async def test_matching_identity(self):
        await require_owned(self.adapter, 'node', 101, *self.ids)

    async def test_wrong_instance_project_environment_deploy_or_attempt(self):
        marker = json.loads(ownership_marker(*self.ids))
        for key in ('instance', 'project', 'environment', 'deploy', 'attempt'):
            with self.subTest(key=key):
                wrong = {**marker, key: str(uuid.uuid4())}
                self.adapter.get_lxc_config.return_value = {'description': json.dumps(wrong)}
                with self.assertRaises(ProxmoxError):
                    await require_owned(self.adapter, 'node', 101, *self.ids)

    async def test_missing_marker_never_stops_or_destroys(self):
        self.adapter.get_lxc_config.return_value = {'hostname': 'shared-name'}
        self.assertFalse(await destroy_lxc_container(self.adapter, 'node', 101,
                                                     ownership=self.ids[:3]))
        self.adapter.stop_lxc.assert_not_awaited()
        self.adapter.destroy_lxc.assert_not_awaited()

    async def test_reused_vmid_after_stop_never_destroyed(self):
        self.adapter.get_lxc_config.side_effect = [
            {'description': ownership_marker(*self.ids)}, {'description': ''}]
        self.assertFalse(await destroy_lxc_container(self.adapter, 'node', 101,
                                                     ownership=self.ids[:3]))
        self.adapter.stop_lxc.assert_awaited_once()
        self.adapter.destroy_lxc.assert_not_awaited()

    async def test_nextid_without_successful_create_cannot_cleanup(self):
        ctx = SimpleNamespace(created_by_attempt=False, vmid=101, target_node='node')
        with self.assertRaises(ProxmoxError):
            await _require_attempt_owned(self.adapter, ctx)
        self.adapter.get_lxc_config.assert_not_awaited()
        self.adapter.destroy_lxc.assert_not_awaited()

    async def test_hostname_only_cleanup_disabled(self):
        with self.assertRaises(TeardownError):
            await teardown_deploy_by_hostname('shared-name', adapter=self.adapter)
        self.adapter.destroy_lxc.assert_not_awaited()

    def test_namespaces_and_project_ids_separate_hostnames(self):
        project, env = self.ids[:2]
        with patch('app.services.resource_ownership.settings.tbd_instance_namespace', 'tbd-dev'):
            dev = resource_hostname(project, env)
            other = resource_hostname(uuid.uuid4(), env)
        with patch('app.services.resource_ownership.settings.tbd_instance_namespace', 'tbd'):
            prod = resource_hostname(project, env)
        self.assertNotEqual(dev, prod)
        self.assertNotEqual(dev, other)
        self.assertLessEqual(len(dev), 63)
