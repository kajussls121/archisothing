#!/bin/env bash
work_dir="tmp"
out_dir="."
profile_to_build="."
ARGS="-v -w $work_dir -o $out_dir $profile_to_build"
echo "Building..."
if [ -d "$work_dir" ]; then
    echo "Removing existing work directory 'tmp'..."
    sudo rm -rf "tmp"
fi
echo "Args: $ARGS"
sudo mkarchiso $ARGS


if [ -d "$work_dir" ]; then
    sudo rm -rf "tmp"
fi
