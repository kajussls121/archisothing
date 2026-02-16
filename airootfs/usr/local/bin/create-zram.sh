#!/bin/bash
set -euo pipefail

GBSIZE=2
ZRAM_DEV="/dev/zram0"
SWAP_IMG="/swap.img"
COMP_ALGO="lz4"


# Clean up any existing zram swap
if [ -e "$ZRAM_DEV" ]; then
    echo "$ZRAM_DEV exists, cleaning up."
    if swapon --summary | grep -q "$ZRAM_DEV"; then
        echo "Swapping off $ZRAM_DEV"
        swapoff "$ZRAM_DEV" || echo "Warning: swapoff $ZRAM_DEV failed"
    fi
    echo "Removing zram module"
    modprobe -r zram || echo "Warning: modprobe -r zram failed"
    sleep 2
fi

# Ensure fallback swap is enabled if not already
if ! swapon --summary | grep -q "$SWAP_IMG"; then
    if [ -f "$SWAP_IMG" ]; then
        echo "Enabling fallback swap $SWAP_IMG"
        swapon "$SWAP_IMG" || echo "Warning: swapon $SWAP_IMG failed"
    else
        echo "Warning: $SWAP_IMG not found, fallback swap not enabled"
    fi
fi

# Set up zram
modprobe zram
if [ ! -e "$ZRAM_DEV" ]; then
    echo "Error: $ZRAM_DEV not created after modprobe"
    exit 1
fi

if [ -w "/sys/block/zram0/comp_algorithm" ]; then
    echo "$COMP_ALGO" > /sys/block/zram0/comp_algorithm
else
    echo "Warning: Cannot set compression algorithm, file not writable"
fi

# Set zram size (in bytes)
ZRAM_SIZE_BYTES=$((($GBSIZE * 1024 * 1024 * 1024)+1)) # +1 so free -h shows the right amount instead of like 40gib, but showing instead 41gib
echo "$ZRAM_SIZE_BYTES" > /sys/block/zram0/disksize

mkswap "$ZRAM_DEV"
if swapon "$ZRAM_DEV"; then
    echo "Successfully enabled swap on $ZRAM_DEV"
    # If fallback swap is enabled, disable it now
    if swapon --summary | grep -q "$SWAP_IMG"; then
        echo "Disabling fallback swap $SWAP_IMG"
        swapoff "$SWAP_IMG" || echo "Warning: swapoff $SWAP_IMG failed"
    fi
else
    echo "Error: swapon $ZRAM_DEV failed"
    exit 1
fi
