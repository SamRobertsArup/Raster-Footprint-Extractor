import osr
import numpy as np
from osgeo.gdalconst import GDT_Byte
from osgeo import gdal
import ogr
import os

raster_path = r"C:\dev\Raster Preparer and ML Vectoriser\tifs\London\IMG_PHR1B_PMS_202005181116549_ORT_599f09d2-67ea-4ec3-ce02-664cfaa06827-001_R1C1.TIF"
out_path = r"C:\dev\Raster Preparer and ML Vectoriser\tifs\polygonised.shp"



def getFlatArray(raster):
    imarray = np.array(raster.ReadAsArray())
    flattenedarray = imarray[0]
    for i in range(1, imarray.shape[0]):
        flattenedarray = np.add(flattenedarray, imarray[i])

    return flattenedarray

if __name__ == "__main__":
    print("opening raster...")
    raster = gdal.Open(raster_path)
    dst_crs = 'EPSG:' + str(osr.SpatialReference(wkt=raster.GetProjection()).GetAttrValue('AUTHORITY', 1))
    # xoff, a, b, yoff, d, e = raster.GetGeoTransform()
    print(f"raster crs: {dst_crs}")

    print("flattening raster...")
    arr = getFlatArray(raster)
    cols, rows = arr.shape[0], arr.shape[1]
    print(f"raster size: ({cols}, {rows})")

    print("delineating footprint...")
    mask = np.zeros(arr.shape, dtype=np.uint8)
    masked_arr = np.logical_xor(arr, mask)
    masked_arr = masked_arr.astype(np.uint8)  # set numpy array datatype equal to gdal datatype (uint8 = GDT_Byte)

    print("outputting temporary masked array...")
    # driver = raster.GetDriver()
    # out_temp_masked = driver.Create(r"C:\dev\Raster Preparer and ML Vectoriser\tifs\outtemp.tif", rows, cols, 1, GDT_Byte)
    # if out_temp_masked is None:
    #     print('Could not create temporary masked tif')
    #
    # # write data
    # outBand = out_temp_masked.GetRasterBand(1)
    # outBand.WriteArray(masked_arr)
    #
    # # write metadata
    # out_temp_masked.SetGeoTransform(raster.GetGeoTransform())
    # out_temp_masked.SetProjection(raster.GetProjection())
    #
    # # save
    # outBand.FlushCache()
    # del out_temp_masked

    drv = ogr.GetDriverByName("ESRI Shapefile")
    if os.path.exists(out_path):
        drv.DeleteDataSource(out_path)

    dst_ds = drv.CreateDataSource(out_path)
    dst_layer = dst_ds.CreateLayer("polygonized", srs=None)  # , geom_type=ogr.wkbMultiPolygon
    # newField = ogr.FieldDefn('RasterVal', ogr.OFTInteger)
    # dst_layer.CreateField(newField)

    print("Polygonising...")
    srcband = gdal.Open(r"C:\dev\Raster Preparer and ML Vectoriser\tifs\test_tif_utm30N.tif").GetRasterBand(1)
    gdal.Polygonize(srcBand=srcband, maskBand=None, outLayer=dst_layer, iPixValField=-1)
    dst_ds.Destroy()
    srcband.FlushCache()
    del srcband, dst_ds
    print("footprint")

