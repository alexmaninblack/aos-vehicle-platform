// SPDX-FileCopyrightText: 2026 maninblack
// SPDX-License-Identifier: Apache-2.0

#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <linux/loop.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#define BACKING_FILE \
    "/var/aos/workdirs/sm/runtimes/.vehicle-data-provider-store.ext4"
#define BACKING_SIZE UINT64_C(536870912)
#define MAX_LOOP_DEVICES 256

static void Fail(const char* format, ...)
{
    va_list arguments;

    fputs("Vehicle data provider loop helper failed: ", stderr);
    va_start(arguments, format);
    vfprintf(stderr, format, arguments);
    va_end(arguments);
    fputc('\n', stderr);
    exit(EXIT_FAILURE);
}

static int OpenBacking(struct stat* metadata)
{
    int descriptor = open(BACKING_FILE, O_RDWR | O_CLOEXEC | O_NOFOLLOW);

    if (descriptor < 0) {
        Fail("cannot open the fixed backing file: %s", strerror(errno));
    }
    if (fstat(descriptor, metadata) != 0) {
        Fail("cannot inspect the fixed backing file: %s", strerror(errno));
    }
    if (!S_ISREG(metadata->st_mode) || metadata->st_uid != 0 ||
        metadata->st_gid != 0 || (metadata->st_mode & 07777) != 0600 ||
        (uint64_t)metadata->st_size != BACKING_SIZE ||
        (uint64_t)metadata->st_blocks * 512 < BACKING_SIZE) {
        Fail("the fixed backing file contract changed");
    }

    return descriptor;
}

static int OpenLoop(int index, int flags)
{
    char path[32];
    int length = snprintf(path, sizeof(path), "/dev/loop%d", index);

    if (length < 0 || (size_t)length >= sizeof(path)) {
        Fail("cannot construct the loop device path");
    }
    return open(path, flags | O_CLOEXEC | O_NOFOLLOW);
}

static bool MatchesBacking(int descriptor, const struct stat* backing)
{
    struct loop_info64 status;

    memset(&status, 0, sizeof(status));
    if (ioctl(descriptor, LOOP_GET_STATUS64, &status) != 0) {
        if (errno == ENXIO) {
            return false;
        }
        Fail("cannot inspect a loop device: %s", strerror(errno));
    }

    return status.lo_device == (uint64_t)backing->st_dev &&
        status.lo_inode == (uint64_t)backing->st_ino;
}

static int FindBackingLoop(const struct stat* backing, int* matches)
{
    int selected = -1;

    *matches = 0;
    for (int index = 0; index < MAX_LOOP_DEVICES; ++index) {
        int descriptor = OpenLoop(index, O_RDONLY);

        if (descriptor < 0) {
            if (errno == ENOENT || errno == ENXIO) {
                continue;
            }
            Fail("cannot open /dev/loop%d: %s", index, strerror(errno));
        }
        if (MatchesBacking(descriptor, backing)) {
            selected = index;
            ++*matches;
        }
        close(descriptor);
    }

    return selected;
}

static void PrintLoop(int index)
{
    if (printf("/dev/loop%d\n", index) < 0) {
        Fail("cannot report the selected loop device");
    }
}

static void Attach(void)
{
    struct stat backing;
    struct loop_info64 status;
    int backingDescriptor = OpenBacking(&backing);
    int matches = 0;
    int selected = FindBackingLoop(&backing, &matches);

    if (matches > 1) {
        Fail("the fixed backing file has multiple loop devices");
    }
    if (matches == 1) {
        close(backingDescriptor);
        PrintLoop(selected);
        return;
    }

    int control = open("/dev/loop-control", O_RDWR | O_CLOEXEC | O_NOFOLLOW);
    if (control < 0) {
        Fail("cannot open loop-control: %s", strerror(errno));
    }
    selected = ioctl(control, LOOP_CTL_GET_FREE);
    close(control);
    if (selected < 0 || selected >= MAX_LOOP_DEVICES) {
        Fail("cannot select a bounded free loop device: %s", strerror(errno));
    }

    int loop = OpenLoop(selected, O_RDWR);
    if (loop < 0) {
        Fail("cannot open the selected loop device: %s", strerror(errno));
    }
    if (ioctl(loop, LOOP_SET_FD, backingDescriptor) != 0) {
        Fail("cannot attach the fixed backing file: %s", strerror(errno));
    }
    memset(&status, 0, sizeof(status));
    status.lo_flags = 0;
    if (ioctl(loop, LOOP_SET_STATUS64, &status) != 0) {
        int savedError = errno;
        ioctl(loop, LOOP_CLR_FD, 0);
        errno = savedError;
        Fail("cannot fix the loop device status: %s", strerror(errno));
    }
    close(loop);
    close(backingDescriptor);

    int verifiedMatches = 0;
    int verified = FindBackingLoop(&backing, &verifiedMatches);
    if (verifiedMatches != 1 || verified != selected) {
        Fail("the attached loop device failed identity verification");
    }
    PrintLoop(selected);
}

static void Detach(void)
{
    struct stat backing;
    int backingDescriptor = OpenBacking(&backing);
    int matches = 0;
    int selected = FindBackingLoop(&backing, &matches);

    close(backingDescriptor);
    if (matches != 1) {
        Fail("the fixed backing file is not attached exactly once");
    }

    int loop = OpenLoop(selected, O_RDWR);
    if (loop < 0) {
        Fail("cannot open the attached loop device: %s", strerror(errno));
    }
    if (ioctl(loop, LOOP_CLR_FD, 0) != 0) {
        Fail("cannot detach the fixed backing file: %s", strerror(errno));
    }
    close(loop);

    int verifiedMatches = 0;
    FindBackingLoop(&backing, &verifiedMatches);
    if (verifiedMatches != 0) {
        Fail("the fixed backing file remains attached");
    }
}

int main(int argc, char* argv[])
{
    if (getuid() != 0 || geteuid() != 0) {
        Fail("the helper must run as real and effective root");
    }
    if (argc != 2) {
        Fail("usage: aos-vehicle-data-provider-loop <attach|detach>");
    }
    if (strcmp(argv[1], "attach") == 0) {
        Attach();
        return EXIT_SUCCESS;
    }
    if (strcmp(argv[1], "detach") == 0) {
        Detach();
        return EXIT_SUCCESS;
    }

    Fail("usage: aos-vehicle-data-provider-loop <attach|detach>");
    return EXIT_FAILURE;
}
