"""UCF24 Dataset Classes

Author: Gurkirt Singh for ucf101-24 dataset

"""

import os
import os.path
import torch
import torch.utils.data as data
import cv2, pickle
import numpy as np

CLASSES = (  # always index 0
        'Basketball', 'BasketballDunk', 'Biking', 'CliffDiving', 'CricketBowling', 'Diving', 'Fencing',
        'FloorGymnastics', 'GolfSwing', 'HorseRiding', 'IceDancing', 'LongJump', 'PoleVault', 'RopeClimbing',
        'SalsaSpin','SkateBoarding', 'Skiing', 'Skijet', 'SoccerJuggling',
        'Surfing', 'TennisSwing', 'TrampolineJumping', 'VolleyballSpiking', 'WalkingWithDog')


class AnnotationTransform(object):
    """
    Same as original
    Transforms a VOC annotation into a Tensor of bbox coords and label index
    Initilized with a dictionary lookup of classnames to indexes
    Arguments:
        class_to_ind (dict, optional): dictionary lookup of classnames -> indexes
            (default: alphabetic indexing of UCF24's 24 classes)
        keep_difficult (bool, optional): keep difficult instances or not
            (default: False)
        height (int): height
        width (int): width
    """

    def __init__(self, class_to_ind=None, keep_difficult=False):
        self.class_to_ind = class_to_ind or dict(
            zip(CLASSES, range(len(CLASSES))))
        self.ind_to_class = dict(zip(range(len(CLASSES)),CLASSES))

    def __call__(self, bboxs, labels, width, height):
        res = []
        for t in range(len(labels)):
            bbox = bboxs[t,:]
            label = labels[t]
            '''pts = ['xmin', 'ymin', 'xmax', 'ymax']'''
            bndbox = []
            for i in range(4):
                cur_pt = max(0,int(bbox[i]) - 1)
                scale =  width if i % 2 == 0 else height
                cur_pt = min(scale, int(bbox[i]))
                cur_pt = float(cur_pt) / scale
                bndbox.append(cur_pt)
            bndbox.append(label)
            res += [bndbox]  # [xmin, ymin, xmax, ymax, label_ind]
            # img_id = target.find('filename').text[:-4]
        return res  # [[xmin, ymin, xmax, ymax, label_ind], ... ]


def readsplitfile(splitfile):
    with open(splitfile, 'r') as f:
        temptrainvideos = f.readlines()
    trainvideos = []
    for vid in temptrainvideos:
        vid = vid.rstrip('\n')
        trainvideos.append(vid)
    return trainvideos


def make_lists(rootpath, imgtype, split=1, fulltest=False):
    imagesDir = rootpath + imgtype + '/'
    # splitfile = rootpath + 'splitfiles/trainlist_new.txt'
    # splitfile_val = rootpath + 'splitfiles/vallist_new.txt'
    splitfile = rootpath + 'splitfiles/trainlist{:02d}.txt'.format(split)
    trainvideos = readsplitfile(splitfile)
    # valvideos = readsplitfile(splitfile_val)
    trainlist = []
    testlist = []
    import collections
    train_vid_frame = collections.defaultdict(list)
    with open(rootpath + 'splitfiles/pyannot.pkl','rb') as fff:
        database = pickle.load(fff)

    train_action_counts = np.zeros(len(CLASSES), dtype=np.int32)
    test_action_counts = np.zeros(len(CLASSES), dtype=np.int32)

    ratios = np.asarray([1.1,0.8,4.7,1.4,0.9,2.6,2.2,3.0,3.0,5.0,6.2,2.7,3.5,3.1,4.3,2.5,4.5,3.4,6.7,3.6,1.6,3.4,0.6,4.3])
    # ratios = np.ones_like(ratios) #TODO:uncomment this line and line 155, 156 to compute new ratios might be useful for JHMDB21
    video_list = []
    vid_last = -100
    train_cnt = 0
    lock = True
    for vid, videoname in enumerate(sorted(database.keys())):
        video_list.append(videoname)
        actidx = database[videoname]['label']
        istrain = True
        step = ratios[actidx]
        numf = database[videoname]['numf']
        lastf = numf-1
        # if videoname in trainvideos:
        #     istrain = True
        # elif videoname in valvideos:
        #     istrain = False
        #     step = ratios[actidx]*2.0
        # else:
        #     continue

        if videoname not in trainvideos:
            istrain = False
            step = ratios[actidx] * 2.0
        if fulltest:
            step = 1
            lastf = numf

        annotations = database[videoname]['annotations']
        num_tubes = len(annotations)

        tube_labels = np.zeros((numf,num_tubes),dtype=np.int16) # check for each tube if present in
        tube_boxes = [[[] for _ in range(num_tubes)] for _ in range(numf)]
        for tubeid, tube in enumerate(annotations):
            # print('numf00', numf, tube['sf'], tube['ef'])
            for frame_id, frame_num in enumerate(np.arange(tube['sf'], tube['ef'], 1)): # start of the tube to end frame of the tube
                label = tube['label']
                assert actidx == label, 'Tube label and video label should be same'
                box = tube['boxes'][frame_id, :]  # get the box as an array
                box = box.astype(np.float32)
                box[2] += box[0]  #convert width to xmax
                box[3] += box[1]  #converst height to ymax
                tube_labels[frame_num, tubeid] = label+1  # change label in tube_labels matrix to 1 form 0
                tube_boxes[frame_num][tubeid] = box  # put the box in matrix of lists

        possible_frame_nums = np.arange(0, lastf, step)
        # print('numf',numf,possible_frame_nums[-1])
        for frame_num in possible_frame_nums: # loop from start to last possible frame which can make a legit sequence
            frame_num = np.int32(frame_num)
            check_tubes = tube_labels[frame_num,:]

            if np.sum(check_tubes>0)>0:  # check if there aren't any semi overlapping tubes
                all_boxes = []
                labels = []
                image_name = imagesDir + videoname+'/{:05d}.jpg'.format(frame_num+1)
                label_name = rootpath + 'labels/' + videoname + '/{:05d}.txt'.format(frame_num + 1)

                assert os.path.isfile(image_name), 'Image does not exist'+image_name
                for tubeid, tube in enumerate(annotations):
                    if tube_labels[frame_num, tubeid]>0:
                        box = np.asarray(tube_boxes[frame_num][tubeid])
                        all_boxes.append(box)
                        labels.append(tube_labels[frame_num, tubeid])

                if istrain: # if it is training video
                    trainlist.append([vid, frame_num+1, np.asarray(labels)-1, np.asarray(all_boxes)])
                    if vid is not vid_last and lock is False:  # and vid_last > 0
                        lock = True
                        if vid_last > 0:
                            train_vid_frame[str(vid_last)].append(train_cnt)

                    if vid is not vid_last and lock is True:
                        train_vid_frame[str(vid)].append(train_cnt)
                        lock = False

                    train_cnt += 1
                    vid_last = vid

                    train_action_counts[actidx] += len(labels)
                else: # if test video and has micro-tubes with GT
                    testlist.append([vid, frame_num+1, np.asarray(labels)-1, np.asarray(all_boxes)])
                    test_action_counts[actidx] += len(labels)
            elif fulltest and not istrain: # if test video with no ground truth and fulltest is trues
                testlist.append([vid, frame_num+1, np.asarray([9999]), np.zeros((1,4))])

    train_vid_frame[str(vid_last)].append(train_cnt)

    for actidx, act_count in enumerate(train_action_counts): # just to see the distribution of train and test sets
        print('train {:05d} test {:05d} action {:02d} {:s}'.format(act_count, test_action_counts[actidx] , int(actidx), CLASSES[actidx]))

    # newratios = train_action_counts/4000
    # print('new   ratios', newratios)
    # print('older ratios', ratios)
    print('Trainlistlen', len(trainlist), ' testlist ', len(testlist))

    return trainlist, testlist, video_list, train_vid_frame


class UCF24Detection(data.Dataset):
    """UCF24 Action Detection Dataset
    to access input images and target which is annotation
    """

    def __init__(self, root, image_set, transform=None, target_transform=None,
                 dataset_name='ucf24', input_type='rgb', full_test=False):

        self.input_type = input_type
        input_type = input_type+'-images'
        self.root = root
        self.CLASSES = CLASSES
        self.image_set = image_set
        self.transform = transform
        self.target_transform = target_transform
        self.name = dataset_name
        self._annopath = os.path.join(root, 'labels/', '%s.txt')
        self._imgpath = os.path.join(root, input_type)
        self.ids = list()
        self.last_vid = []

        trainlist, testlist, video_list, train_vid_frame = make_lists(root, input_type, split=1, fulltest=full_test)
        self.video_list = video_list
        self.train_vid_frame = train_vid_frame

        if self.image_set == 'train':
            self.ids = trainlist
        elif self.image_set == 'test':
            self.ids = testlist
        else:
            print('spacify correct subset ')

    def __getitem__(self, index):
        im, gt, img_index= self.pull_item(index)

        return im, gt, img_index

    def __len__(self):
        return len(self.ids)

    def pull_item(self, index):
        annot_info = self.ids[index]
        frame_num = annot_info[1]
        video_id = annot_info[0]
        videoname = self.video_list[video_id]
        img_name = self._imgpath + '/{:s}/{:05d}.jpg'.format(videoname, frame_num)
        vid = img_name.split('/')[-2]
        change_vid = False
        if vid != self.last_vid:
            change_vid = True
        self.last_vid = vid
        # print(img_name)
        img = cv2.imread(img_name)
        height, width, channels = img.shape

        target = self.target_transform(annot_info[3], annot_info[2], width, height)


        if self.transform is not None:
            target = np.array(target)
            img, boxes, labels = self.transform(img, target[:, :4], target[:, 4])
            img = img[:, :, (2, 1, 0)]
            # img = img.transpose(2, 0, 1)
            target = np.hstack((boxes, np.expand_dims(labels, axis=1)))
        # print(height, width,target)
        return torch.from_numpy(img).permute(2, 0, 1), target, [index, change_vid]
        # return torch.from_numpy(img), target, height, width


def detection_collate(batch):
    """Custom collate fn for dealing with batches of images that have a different
    number of associated object annotations (bounding boxes).
    Arguments:
        batch: (tuple) A tuple of tensor images and lists of annotations
    Return:
        A tuple containing:
            1) (tensor) batch of images stacked on their 0 dim
            2) (list of tensors) annotations for a given image are stacked on 0 dim
    """

    targets = []
    imgs = []
    image_ids = []
    for sample in batch:
        imgs.append(sample[0])
        targets.append(torch.FloatTensor(sample[1]))
        image_ids.append(sample[2])
    return torch.stack(imgs, 0), targets, image_ids