#!/bin/bash

mkdir -p output/pngs
pdftoppm output/album.pdf output/pngs/page -f 1 -l 4 -png -progress -r 300 -aa yes -aaVector yes
#magick output/pngs/page-02.png -density 300 -units PixelsPerInch -gravity center -background "#1a1a1a" -extent "%[fx:31*300/2.54]x%[fx:24*300/2.54]" output/pngs/bg-02.png