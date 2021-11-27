#
import numpy as np
import scipy.io as sio
import scipy.misc
from keras.preprocessing import image
from PIL import Image
from skimage.transform import rotate, resize
from skimage.measure import label, regionprops
from time import time
import cv2

from mnet_utils import pro_process, BW_img, disc_crop, mk_dir, return_list
import Model_DiscSeg as DiscModel
import Model_MNet as MNetModel

DiscROI_size = 600
DiscSeg_size = 640
CDRSeg_size = 400

test_data_path = './test_img/'
data_save_path = mk_dir('./result/')

file_test_list = return_list(test_data_path, '.jpg')

DiscSeg_model = DiscModel.DeepModel(size_set=DiscSeg_size)
DiscSeg_model.load_weights('./deep_model/Model_DiscSeg_ORIGA.h5')

CDRSeg_model = MNetModel.DeepModel(size_set=CDRSeg_size)
CDRSeg_model.load_weights('./deep_model/Model_MNet_REFUGE.h5')

for lineIdx in range(len(file_test_list)):

    temp_txt = file_test_list[lineIdx]
    # load image
    org_img = np.asarray(image.load_img(test_data_path + temp_txt))
    # Disc region detection by U-Net
    temp_img = resize(org_img, (DiscSeg_size, DiscSeg_size, 3))*255
    temp_img = np.reshape(temp_img, (1,) + temp_img.shape)
    disc_map = DiscSeg_model.predict([temp_img])
    disc_map = BW_img(np.reshape(disc_map, (DiscSeg_size, DiscSeg_size)), 0.5)

    regions = regionprops(label(disc_map))
    C_x = int(regions[0].centroid[0] * org_img.shape[0] / DiscSeg_size)
    C_y = int(regions[0].centroid[1] * org_img.shape[1] / DiscSeg_size)
    disc_region, err_xy, crop_xy = disc_crop(org_img, DiscROI_size, C_x, C_y)

    # Disc and Cup segmentation by M-Net
    run_start = time()
    Disc_flat = rotate(cv2.linearPolar(disc_region, (DiscROI_size/2, DiscROI_size/2),
                                       DiscROI_size/2, cv2.WARP_FILL_OUTLIERS), -90)

    temp_img = pro_process(Disc_flat, CDRSeg_size)
    temp_img = np.reshape(temp_img, (1,) + temp_img.shape)
    [_, _, _, _, prob_10] = CDRSeg_model.predict(temp_img)
    run_end = time()

    from skimage.transform import resize
    # Extract mask
    prob_map = np.reshape(prob_10, (prob_10.shape[1], prob_10.shape[2], prob_10.shape[3]))
    disc_map = resize(prob_map[:, :, 0], (DiscROI_size, DiscROI_size))
    cup_map = resize(prob_map[:, :, 1], (DiscROI_size, DiscROI_size))
    disc_map[-round(DiscROI_size / 3):, :] = 0
    cup_map[-round(DiscROI_size / 2):, :] = 0
    De_disc_map = cv2.linearPolar(rotate(disc_map, 90), (DiscROI_size/2, DiscROI_size/2),
                                  DiscROI_size/2, cv2.WARP_FILL_OUTLIERS + cv2.WARP_INVERSE_MAP)
    De_cup_map = cv2.linearPolar(rotate(cup_map, 90), (DiscROI_size/2, DiscROI_size/2),
                                 DiscROI_size/2, cv2.WARP_FILL_OUTLIERS + cv2.WARP_INVERSE_MAP)

    De_disc_map = np.array(BW_img(De_disc_map, 0.5), dtype=int)
    De_cup_map = np.array(BW_img(De_cup_map, 0.5), dtype=int)

    print(' Processing Img ' + str(lineIdx+1) + ' : ' + temp_txt + ', running time: ' + str(run_end - run_start))

    # Save raw mask
    ROI_result = np.array(BW_img(De_disc_map, 0.5), dtype=int) + np.array(BW_img(De_cup_map, 0.5), dtype=int)
    Img_result = np.zeros((org_img.shape[0], org_img.shape[1]), dtype=np.int8)
    Img_result[crop_xy[0]:crop_xy[1], crop_xy[2]:crop_xy[3], ] = ROI_result[err_xy[0]:err_xy[1], err_xy[2]:err_xy[3], ]
    save_result = Image.fromarray((Img_result*127).astype(np.uint8))
    save_result.save(data_save_path + temp_txt[:-4] + '.png')
