"""Module for dropping root privileges on POSIX systems.

Inspired by / sources:
- https://stackoverflow.com/a/2699996
- https://stackoverflow.com/a/44689594
- https://pythonhosted.org/python-prctl/
"""

import os, pwd, grp
import platform


def drop_privileges(uid_name='nobody', gid_name=None):
    """
    Drop root privileges by pretending to be user uid_name
    in group gid_name (defaults to primary)

    On Linux will also continue to give the process the NET_BIND_SERVICE capability.
    """

    # Get the uid/gid from the name
    pwd_user = pwd.getpwnam(uid_name)
    running_uid = pwd_user.pw_uid
    if gid_name is None:
        # set gid to be primary group of user
        running_gid = pwd_user.pw_gid
    else:
        running_gid = grp.getgrnam(gid_name).gr_gid

    # Set groups privileges
    os.setgroups(os.getgrouplist(uid_name, running_gid))

    # Try setting the new gid
    os.setgid(running_gid)

    # Linux: Limit capabilities to only being able to change uid and binding ports below 1024
    is_linux = False
    if platform.system().lower().startswith('lin'):
        is_linux = True
        import prctl
        prctl.securebits.keep_caps = True
        prctl.securebits.no_setuid_fixup = True
        prctl.capbset.limit(prctl.CAP_NET_BIND_SERVICE, prctl.CAP_SETUID)
        try:
            prctl.cap_permitted.limit(prctl.CAP_NET_BIND_SERVICE, prctl.CAP_SETUID)
        except PermissionError:
            pass
        prctl.cap_effective.limit(prctl.CAP_NET_BIND_SERVICE, prctl.CAP_SETUID)

    # Try setting the new uid
    os.setuid(running_uid)

    # We still need to have our caps.
    if is_linux:
        assert prctl.cap_permitted.net_bind_service
        assert prctl.cap_effective.net_bind_service

    # Ensure a very conservative umask
    os.umask(0o22)

    os.environ['HOME'] = pwd_user.pw_dir

    # Linux: Remove setuid cap again
    if is_linux:
        try:
            prctl.capbset.drop(prctl.CAP_SETUID)
        except PermissionError:
            return  # if this is the case, linux has already done this for us
        try:
            prctl.cap_permitted.drop(prctl.CAP_SETUID)
        except PermissionError:
            pass
        prctl.cap_effective.drop(prctl.CAP_SETUID)


