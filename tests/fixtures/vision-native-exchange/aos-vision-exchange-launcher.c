/* SPDX-FileCopyrightText: 2026 maninblack
 * SPDX-License-Identifier: Apache-2.0 */
#define _GNU_SOURCE
#include <grp.h>
#include <limits.h>
#include <pwd.h>
#include <stdio.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <unistd.h>

/* The proof uses one compile-time fixed, root-owned /run file. It is never
 * selected by an application, command-line argument or environment variable.
 * The permanent build uses only the native OEM active slot below. */
int main(int argc, char **argv) {
    (void)argv;
    struct passwd *user=getpwnam("aos-vision-exchange");
    struct group *group=getgrnam("aos-vision-exchange");
    char entry[PATH_MAX];
    if (argc!=1 || !user || !group || !user->pw_uid || !group->gr_gid ||
        getuid()!=user->pw_uid || geteuid()!=user->pw_uid ||
        getgid()!=group->gr_gid || getegid()!=group->gr_gid ||
        prctl(PR_SET_NO_NEW_PRIVS,1,0,0,0)) goto fail;
#ifdef AOS_VISION_EXCHANGE_PROOF
    snprintf(entry,sizeof(entry),"/run/aos-vision-services-proof/camera-access");
#else
    const char *root="/var/aos/workdirs/sm/runtimes/systemd-slot-camera-access";
    char slot[16];
    snprintf(entry,sizeof(entry),"%s/active",root);
    ssize_t n=readlink(entry,slot,sizeof(slot)-1);
    if (n<0 || n>=(ssize_t)sizeof(slot)-1) goto fail;
    slot[n]=0;
    if (strcmp(slot,"slots/a") && strcmp(slot,"slots/b")) goto fail;
    snprintf(entry,sizeof(entry),"%s/%s/bin/camera-access",root,slot);
#endif
    struct stat info;
    if (lstat(entry,&info) || !S_ISREG(info.st_mode) || info.st_uid ||
        (info.st_mode&0022) || !(info.st_mode&0111)) goto fail;
    char *args[]={"/usr/bin/python3","-I","-B",entry,"--exchange",NULL};
    execv(args[0],args);
fail:
    fputs("VISION_EXCHANGE_LAUNCH_REJECTED\n",stderr);return 1;
}
