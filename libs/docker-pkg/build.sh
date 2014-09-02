#!/bin/bash
##
## Build script for Docker custom package
## @author: Thibault BRONCHAIN
##
## (c) 2014 MadeiraCloud LTD.
##

USAGE="$0 deb|rpm [path]"

function deb() {
    PREV=$PWD
    if [ "$1" != "" ]; then
        cd $1
    fi
    cd deb-build
    # build here
    apt-get -y install make devscripts
    dpkg-buildpackage -uc -us
    if [ $? -eq 0 ]; then
        echo "Build succeed."
    else
        echo "Build failed."
    fi
    cd $PREV
}

function rpm() {
    PREV=$PWD
    if [ "$1" != "" ]; then
        cd $1
    fi
    cd rpm-build
    # build here
    if [ $? -eq 0 ]; then
        echo "Build succeed."
    else
        echo "Build failed."
    fi
    cd $PREV
}

case $1 in
    deb)
        deb $2
        ;;
    rpm)
        rpm $2
        ;;
    *)
        echo -e "syntax error\nusage: $USAGE"
        ;;
esac
