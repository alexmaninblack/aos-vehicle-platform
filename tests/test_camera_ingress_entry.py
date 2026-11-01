# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Unit fixtures for strict nonroot entry; no credential or network use."""
from pathlib import Path
import sys
import stat
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'camera-access/src'))
from aos_camera_access import ingress_main as m
from aos_camera_access.core import CameraError


class EntryTests(unittest.TestCase):
    def test_root_owned_systemd_acl_is_exact_not_a_group_or_world_grant(self):
        undefined=2**32-1
        entries=[(1,4,undefined),(2,4,992),(4,0,undefined),(16,4,undefined),(32,0,undefined)]
        encode=lambda rows:struct.pack('<I',2)+b''.join(struct.pack('<HHI',*v) for v in rows)
        info=SimpleNamespace(st_mode=stat.S_IFREG|0o440,st_uid=0,st_gid=0,st_nlink=1)
        m.credential_access(info,992,encode(entries))
        for index,replacement in ((1,(2,4,5000)),(2,(4,4,undefined)),(4,(32,4,undefined))):
            bad=list(entries);bad[index]=replacement
            with self.assertRaises(CameraError):m.credential_access(info,992,encode(bad))
        with self.assertRaises(CameraError):m.credential_access(info,992,encode(entries+[entries[1]]))
        with self.assertRaises(CameraError):m.credential_access(info,992,None)
        owned=SimpleNamespace(st_mode=stat.S_IFREG|0o400,st_uid=992,st_gid=990,st_nlink=1)
        m.credential_access(owned,992,None)
        owned.st_mode|=0o004
        with self.assertRaises(CameraError):m.credential_access(owned,992,None)
    def test_identity_requires_exact_uid_group_domain_nnp_and_empty_caps(self):
        status='NoNewPrivs: 1\n'+''.join(k+': 0\n' for k in ('CapEff','CapInh','CapPrm','CapAmb','CapBnd'))
        with patch.object(m.pwd,'getpwnam',return_value=SimpleNamespace(pw_uid=992)), \
                patch.object(m.grp,'getgrnam',return_value=SimpleNamespace(gr_gid=990)), \
                patch.object(m.os,'getuid',return_value=992) as uid,patch.object(m.os,'geteuid',return_value=992), \
                patch.object(m.os,'getgid',return_value=990),patch.object(m.os,'getegid',return_value=990), \
                patch.object(Path,'read_text',side_effect=[status,'system_u:system_r:camera_ingress_t:s0\0']) as read:
            m.identity()
            uid.return_value=0
            with self.assertRaisesRegex(CameraError,'IDENTITY'):m.identity()
            uid.return_value=992
            for value in (status.replace('NoNewPrivs: 1','NoNewPrivs: 0'),status.replace('CapEff: 0','CapEff: 1')):
                read.side_effect=[value]
                with self.assertRaisesRegex(CameraError,'PRIVILEGE'):m.identity()
            read.side_effect=[status,'system_u:system_r:camera_access_t:s0']
            with self.assertRaisesRegex(CameraError,'DOMAIN'):m.identity()

    def test_unowned_credential_directory_rejected_before_any_file_read(self):
        with patch.dict(m.os.environ,{'CREDENTIALS_DIRECTORY':'/tmp/foreign'}),patch.object(Path,'read_bytes') as read:
            with self.assertRaisesRegex(CameraError,'CREDENTIAL_OWNER'):m.credentials()
            read.assert_not_called()

    def test_service_is_outgoing_only_and_has_no_boot_enable_or_capability(self):
        text=(Path(__file__).resolve().parents[1]/'meta-aos-vehicle-platform/recipes-aos/aos-camera-access-platform/files/aos-camera-ingress.service').read_text()
        for value in ('CapabilityBoundingSet=\n','AmbientCapabilities=\n','SocketBindDeny=any','IPAddressDeny=any','IPAddressAllow=10.0.0.1/32','RestrictAddressFamilies=AF_UNIX AF_INET'):
            self.assertIn(value,text)
        self.assertNotIn('WantedBy=',text);self.assertNotIn('ExecStart=/bin/sh',text)


if __name__=='__main__':unittest.main()
