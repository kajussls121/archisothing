#!/bin/env bash
work_dir="tmp"
out_dir="."
profile_to_build="."
ARGS="-v -w $work_dir -o $out_dir $profile_to_build"
if [ -d "$work_dir" ]; then
    echo "Removing existing work directory '$work_dir'..."
    sudo rm -rf "$work_dir"
fi
echo "Building..."
echo "Args: $ARGS"
sudo mkarchiso $ARGS


if [ -d "$work_dir" ]; then
    sudo rm -rf "$work_dir"
fi
