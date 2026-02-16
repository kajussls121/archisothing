#!/bin/env bash
work_dir="tmp"
out_dir="."
profile_to_build="."
ARGS="-v -w $work_dir -o $out_dir $profile_to_build"

echo "Copying python stuff to airootfs"
cp archiso-thing_installscript/*.py archiso-thing_installscript/launch.sh airootfs/usr/local/bin -f # Overwrite any files already existing

if [ -d "$work_dir" ]; then
    read -p "Do you want to remove the work directory before running mkarchiso? (y/n): " remove_work_dir
    if [[ "$remove_work_dir" =~ ^[Yy]$ ]]; then
        echo "Removing existing work directory '$work_dir'..."
        sudo rm -rf "$work_dir"
    fi
fi
echo "Building..."
echo "Args: $ARGS"
sudo mkarchiso $ARGS


if [ -d "$work_dir" ]; then
    read -p "Do you want to remove the work directory? (y/n): " remove_work_dir
    if [[ "$remove_work_dir" =~ ^[Yy]$ ]]; then
        sudo rm -rf "$work_dir"
    fi
fi
