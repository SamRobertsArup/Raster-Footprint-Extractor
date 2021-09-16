from osgeo import gdal, osr, ogr
import numpy as np
import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon,Point,MultiPoint, LineString
import math
import tqdm
from shapely import affinity


raster_path = r"C:\dev\Raster Preparer and ML Vectoriser\tifs\London\IMG_PHR1B_PMS_202005181116549_ORT_599f09d2-67ea-4ec3-ce02-664cfaa06827-001_R1C1.TIF"
out_path = r"C:\dev\Raster Preparer and ML Vectoriser\tifs\test_pixel.shp"

raster = gdal.Open(raster_path)
dst_crs = 'EPSG:'+str(osr.SpatialReference(wkt=raster.GetProjection()).GetAttrValue('AUTHORITY',1))
xoff, a, b, yoff, d, e = raster.GetGeoTransform()


# todo this should be placed in a function
# check if raster in UTM system. Re-projects if not.
if not dst_crs.split(":")[1].startswith('0') or not dst_crs.split(":")[1].startswith('326') or not dst_crs.split(":")[1].startswith('327'):
    determineUTMtif = None
    utm_band = str((math.floor((xoff + 180) / 6) % 60) + 1)
    if len(utm_band) == 1:
        utm_band = '0' + utm_band
    if yoff >= 0:
        epsg_code = '326' + utm_band
    else:
        epsg_code = '327' + utm_band
    dst_crs = 'EPSG:' + str(epsg_code)
    outputESPG = ''.join(ch for ch in dst_crs if ch.isalnum())

    # re-project
    print("Reprojecting tif into " + dst_crs)
    reprojected_raster_path = "\\".join(raster_path.split(".")[:-1]) + "_reprojected.tif"
    gdal.Warp(reprojected_raster_path, raster_path, format="GTiff", options=["COMPRESS=LZW", "TILED=YES"], dstSRS=dst_crs)

    # open new shiny UTM raster
    del raster
    raster = gdal.Open(reprojected_raster_path)
    dst_crs = 'EPSG:' + str(osr.SpatialReference(wkt=raster.GetProjection()).GetAttrValue('AUTHORITY', 1))
    xoff, a, b, yoff, d, e = raster.GetGeoTransform()


def outputResult(pnts):
    # # IGNORE (retained for future debugging) # vector_footprintXY = affinity.rotate(LineString(pnts), 180, (xoff, yoff))

    # I can't tell you why the rotation is required
    # buffer fixes self intersecting geometries
    # max function retains largest of the multipolygons resultant (shouldn't be needed if it worked perfectly)
    vector_footprint = affinity.rotate(Polygon(pnts).buffer(0), 180, (xoff, yoff))
    if vector_footprint.geom_type == 'MultiPolygon':
        vector_footprint = max(vector_footprint, key=lambda a: a.area)

    print("outputting...")
    geoDF = gpd.GeoDataFrame(pd.DataFrame(['p1'], columns=['geom']),
                             crs={'init': dst_crs},
                             geometry=[vector_footprint])
    geoDF.to_file(r'C:\dev\Raster Preparer and ML Vectoriser\tifs\mosaic.shp')


def getFlatArray(raster):
    imarray = np.array(raster.ReadAsArray())
    flattenedarray = imarray[0]
    for i in range(1, imarray.shape[0]):
        flattenedarray = np.add(flattenedarray, imarray[i])

    return flattenedarray


def pixel2point(pxl):
    x,y = pxl
    posY = a * x + b * y + yoff
    posX = d * x + e * y + xoff
    posX += (a/2)  # offset gives centre of pixel
    posY += (a/2)
    return Point(posX, posY)


def getFirstPixel(arr):
    for x in range(0, arr.shape[0] - 1):
        for y in range(0, arr.shape[1] - 1):
            if containsData(arr[x, y]):
                pixel = (x, y)
                return pixel


def getNeighboursGrid(pxl, maxX, maxY, radius):
    x0, y0 = pxl
    neighbours = []

    bbox_min_x = x0-radius
    bbox_max_x = x0+radius
    bbox_min_y = y0-radius
    bbox_max_y = y0+radius

    # get sides of square
    for x in range(bbox_min_x, bbox_max_x, 1):  # top
        neighbours += [(x, bbox_min_y)]
    for y in range(bbox_min_y, bbox_max_y, 1):  # right
        neighbours += [(bbox_max_x, y)]
    for x in range(bbox_max_x, bbox_min_x, -1):  # bottom
        neighbours += [(x, bbox_max_y)]
    for y in range(bbox_max_y, bbox_min_y, -1):  # left
        neighbours += [(bbox_min_x, y)]

    # ensure neighbours are within image (using slice to avoid modify list as iter):
    for n in neighbours[:]:
        if n[0] < 0 or n[0] >= maxX or n[1] < 0 or n[1] >= maxY:
            neighbours.remove(n)

    return neighbours


def containsData(pixel_val):
    if int(pixel_val) != 0:
        return True
    else:
        return False


def moveHere(pxl, pixels_visited, arr, maxX, maxY):
    x,y = pxl
    if (pxl not in pixels_visited and containsData(arr[x,y])):  # Pixel hasn't been visited and has data
        if (x+1 >= maxX or x-1 < 0 or y+1 >= maxY or y-1 < 0 ) or \
                (not containsData(arr[x+1,y]) or not containsData(arr[x-1,y]) or  # at least one neigbour has no data
                not containsData(arr[x,y+1]) or not containsData(arr[x,y-1])):    # or is beyond the images bounds
            return True
    else:
        return False


def getPixels(pxl, arr):
    print("delineating footprint...")
    maxX, maxY = arr.shape[0], arr.shape[1]
    neighbours_offset = 1
    options = True
    pixels = [pxl]
    while options == True:
        pixel_neighbours = getNeighboursGrid(pxl, maxX, maxY, neighbours_offset)
        for i, neighbour in enumerate(pixel_neighbours):
            if moveHere(neighbour, pixels, arr, maxX, maxY):
                pixels.append(neighbour)
                pxl = neighbour
                neighbours_offset = 1
                break
            if i == len(pixel_neighbours)-1:
                neighbours_offset += 1
                break
            if neighbours_offset >= 10:  # unsure why this must be so high, doesn't work if it isn't however
                options = False

    print("footprint acquired!")
    return pixels




if __name__ == "__main__":
    arr = getFlatArray(raster)
    starting_pixel = getFirstPixel(arr)

   # outputSinglePixel(starting_pixel)

    pixels = getPixels(starting_pixel, arr)
    pnts = [pixel2point(pxl) for pxl in pixels]

    outputResult(pnts=pnts)



# ARCHIVED FUNCTIONS

# used to debug
def outputSinglePixel(pxl):
    gpd.GeoDataFrame(pd.DataFrame(['p1'], columns=['geom']),
                     crs={'init': dst_crs},
                     geometry=[affinity.rotate(Point(pixel2point(pxl)), 180, (xoff, yoff))]).to_file(out_path)


# should work but doesn't... no data determined in visually verified data filled pixels - idek!!
def getNeighbours(pxl, maxX, maxY):
    #     812
    # ^   7o3   returns all 8 neighbours around o, which respresents pxl if the neighbour is in the image
    # y/1 654   pixels must be checked in order proscribed here!!
    #    x/0 >
    pixelNeighbours = []

    if pxl[1] + 1 < maxY:
        pixelNeighbours += [(pxl[0], pxl[1] + 1)]  # 1
    if pxl[0] + 1 < maxX and pxl[1] + 1 < maxY:
        pixelNeighbours += [(pxl[0] + 1, pxl[1] + 1)]  # 2
    if pxl[0] + 1 < maxX:
        pixelNeighbours += [(pxl[0] + 1, pxl[1])]  # 3
    if pxl[0] + 1 < maxX and pxl[1] - 1 >= 0:
        pixelNeighbours += [(pxl[0] + 1, pxl[1] - 1)]  # 4
    if pxl[1] - 1 >= 0:
        pixelNeighbours += [(pxl[0], pxl[1] - 1)]  # 5
    if pxl[0] - 1 >= 0 and pxl[1] - 1 >= 0:
        pixelNeighbours += [(pxl[0] - 1, pxl[1] - 1)]  # 6
    if pxl[0] - 1 >= 0:
        pixelNeighbours += [(pxl[0] - 1, pxl[1])]  # 7
    if pxl[0] - 1 >= 0 and pxl[1] + 1 < maxY:
        pixelNeighbours += [(pxl[0] - 1, pxl[1] + 1)]  # 8

    return pixelNeighbours

# doesnt work as consitent order required
def getNeighboursMidpointCircle(pxl, radius, maxX, maxY):
    x0, y0 = pxl

    neighbours = []
    f = 1 - radius
    ddf_x = 1
    ddf_y = -2 * radius
    x = 0
    y = radius
    neighbours+=[(x0, y0 + radius)]
    neighbours+=[(x0, y0 - radius)]
    neighbours+=[(x0 + radius, y0)]
    neighbours+=[(x0 - radius, y0)]

    while x < y:
        if f >= 0:
            y -= 1
            ddf_y += 2
            f += ddf_y
        x += 1
        ddf_x += 2
        f += ddf_x
        neighbours+=[(x0 + x, y0 + y)]
        neighbours+=[(x0 - x, y0 + y)]
        neighbours+=[(x0 + x, y0 - y)]
        neighbours+=[(x0 - x, y0 - y)]
        neighbours+=[(x0 + y, y0 + x)]
        neighbours+=[(x0 - y, y0 + x)]
        neighbours+=[(x0 + y, y0 - x)]
        neighbours+=[(x0 - y, y0 - x)]

    # ensure neighbours are within image:
    for n in neighbours:
        if n[0] < 0 or n[0] > maxX or n[1] < 0 or n[1] > maxY:
            neighbours.remove(n)

    return neighbours