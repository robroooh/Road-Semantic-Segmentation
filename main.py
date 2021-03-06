import os.path
import tensorflow as tf
import helper
import warnings
import numpy as np
from distutils.version import LooseVersion
import project_tests as tests

# Check TensorFlow Version
assert LooseVersion(tf.__version__) >= LooseVersion(
    '1.0'), 'Please use TensorFlow version 1.0 or newer.  You are using {}'.format(tf.__version__)
print('TensorFlow Version: {}'.format(tf.__version__))

# Check for a GPU
if not tf.test.gpu_device_name():
    warnings.warn('No GPU found. Please use a GPU to train your neural network.')
else:
    print('Default GPU Device: {}'.format(tf.test.gpu_device_name()))

LOGDIR = "tensorboard_log/"

def load_vgg(sess, vgg_path):
    """
    Load Pretrained VGG Model into TensorFlow.
    :param sess: Tensor Flow Session
    :param vgg_path: Path to vgg folder, containing "variables/" and "saved_model.pb"
    :return: Tuple of Tensors from VGG model (image_input, keep_prob, layer3_out, layer4_out, layer7_out)
    """
    #   Use tf.saved_model.loader.load to load the model and weights

    vgg_tag = 'vgg16'
    vgg_input_tensor_name = 'image_input:0'
    vgg_keep_prob_tensor_name = 'keep_prob:0'
    vgg_layer3_out_tensor_name = 'layer3_out:0'
    vgg_layer4_out_tensor_name = 'layer4_out:0'
    vgg_layer7_out_tensor_name = 'layer7_out:0'

    tf.saved_model.loader.load(sess, [vgg_tag], vgg_path)
    with tf.name_scope("Encoder"):
        image_input = tf.get_default_graph().get_tensor_by_name(vgg_input_tensor_name)
        # image_input.name = "Image Input"
        keepprob_out = tf.get_default_graph().get_tensor_by_name(vgg_keep_prob_tensor_name)
        layer3_out = tf.get_default_graph().get_tensor_by_name(vgg_layer3_out_tensor_name)
        # layer3_out.name = "Layer 3"
        layer4_out = tf.get_default_graph().get_tensor_by_name(vgg_layer4_out_tensor_name)
        # layer4_out.name = "Layer 4"
        layer7_out = tf.get_default_graph().get_tensor_by_name(vgg_layer7_out_tensor_name)
        # layer7_out.name = "Layer 7"
    return image_input, keepprob_out, layer3_out, layer4_out, layer7_out
tests.test_load_vgg(load_vgg, tf)


def layers(vgg_layer3_out, vgg_layer4_out, vgg_layer7_out, num_classes):
    """
    Create the layers for a fully convolutional network.
    Build skip-layers using the vgg layers.
    :param vgg_layer7_out: TF Tensor for VGG Layer 3 output
    :param vgg_layer4_out: TF Tensor for VGG Layer 4 output
    :param vgg_layer3_out: TF Tensor for VGG Layer 7 output
    :param num_classes: Number of classes to classify
    :return: The Tensor for the last layer of output
    """
    with tf.name_scope("1x1"):
        layer7_conv1x1 = tf.layers.conv2d(vgg_layer7_out, num_classes, 1, padding="SAME",
                                          kernel_regularizer=tf.contrib.layers.l2_regularizer(1e-3),
                                          kernel_initializer=tf.truncated_normal_initializer(stddev=0.01),
                                          name='layer7_conv1x1')
        layer4_conv1x1 = tf.layers.conv2d(vgg_layer4_out, num_classes, 1, padding="SAME",
                                          kernel_regularizer=tf.contrib.layers.l2_regularizer(1e-3),
                                          kernel_initializer=tf.truncated_normal_initializer(stddev=0.01),
                                          name='layer4_conv1x1')
        layer3_conv1x1 = tf.layers.conv2d(vgg_layer3_out, num_classes, 1, padding="SAME",
                                          kernel_regularizer=tf.contrib.layers.l2_regularizer(1e-3),
                                          kernel_initializer=tf.truncated_normal_initializer(stddev=0.01),
                                          name="layer3_conv1x1")

    with tf.name_scope("conv2d_transpose"):
        # 2xConv7
        layer7_conv1x1_upsamp = tf.layers.conv2d_transpose(layer7_conv1x1,
                                                           num_classes, 4,
                                                           strides=2,
                                                           padding="SAME",
                                                           kernel_regularizer=tf.contrib.layers.l2_regularizer(1e-3),
                                                           kernel_initializer=tf.truncated_normal_initializer(stddev=0.01),
                                                           name="layer7_conv1x1_upsamp")
    with tf.name_scope("Add_Layer"):
       combine74 = tf.add(layer4_conv1x1, layer7_conv1x1_upsamp, name="combine74")


    with tf.name_scope("conv2d_transpose"):
        # 2xConv4
        combine74_upsamp = tf.layers.conv2d_transpose(combine74,
                                                       num_classes, 4,
                                                       strides=2,
                                                       padding="SAME",
                                                       kernel_regularizer=tf.contrib.layers.l2_regularizer(1e-3),
                                                       kernel_initializer=tf.truncated_normal_initializer(stddev=0.01),
                                                       name="combine74_upsamp")

    with tf.name_scope("Add_Layer"):
        output = tf.add(layer3_conv1x1, combine74_upsamp, name="combine74_3")

    with tf.name_scope("conv2d_transpose"):
        # upsample the output to 8x
        output_upsamp = tf.layers.conv2d_transpose(output,
                                                   num_classes, 16,
                                                   strides=8,
                                                   padding="SAME",
                                                   kernel_regularizer=tf.contrib.layers.l2_regularizer(1e-3),
                                                   kernel_initializer=tf.truncated_normal_initializer(stddev=0.01),
                                                   name="output_upsamp")

    return output_upsamp
tests.test_layers(layers)


def optimize(nn_last_layer, correct_label, learning_rate, num_classes):
    """
    Build the TensorFLow loss and optimizer operations.
    :param nn_last_layer: TF Tensor of the last layer in the neural network
    :param correct_label: TF Placeholder for the correct label image
    :param learning_rate: TF Placeholder for the learning rate
    :param num_classes: Number of classes to classify
    :return: Tuple of (logits, train_op, cross_entropy_loss)
    """
    logits = tf.reshape(nn_last_layer, (-1, num_classes))
    miou_label = tf.reshape(correct_label[:,:,:,1], [-1])
    correct_label = tf.reshape(correct_label, (-1, num_classes))
    with tf.name_scope("xent"):
        cross_entropy_loss = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(logits=logits, labels=correct_label))
        tf.summary.scalar("xent", cross_entropy_loss)

    with tf.name_scope("train"):
        train_op = tf.train.AdamOptimizer(learning_rate).minimize(cross_entropy_loss)

    with tf.name_scope("mIOU"):
        meaniou_op, mean_iou_update_op = tf.metrics.mean_iou(miou_label, tf.nn.softmax(logits)[:,1] > 0.5,num_classes)
    return logits, train_op, cross_entropy_loss, meaniou_op, mean_iou_update_op
# tests.test_optimize(optimize)


def train_nn(sess, epochs, batch_size, get_batches_fn, train_op, cross_entropy_loss, input_image,
             correct_label, keep_prob, learning_rate, meaniou_op, mean_iou_update_op, get_batches_fn_valid):
    """
    Train neural network and print out the loss during training.
    :param sess: TF Session
    :param epochs: Number of epochs
    :param batch_size: Batch size
    :param get_batches_fn: Function to get batches of training data.  Call using get_batches_fn(batch_size)
    :param train_op: TF Operation to train the neural network
    :param cross_entropy_loss: TF Tensor for the amount of loss
    :param input_image: TF Placeholder for input images
    :param correct_label: TF Placeholder for label images
    :param keep_prob: TF Placeholder for dropout keep probability
    :param learning_rate: TF Placeholder for learning rate
    """
    sess.run(tf.global_variables_initializer())
    sess.run(tf.local_variables_initializer())
    writer = tf.summary.FileWriter(LOGDIR+"1")
    writer.add_graph(sess.graph)
    train_count = 1
    # saver = tf.train.Saver()
    #
    summ = tf.summary.merge_all()
    for epoch in range(epochs):
        for image, label in get_batches_fn(batch_size):
            # print("=========================")
            # print(image.shape)
            # print(label.shape)
            tf.summary.image('input', image[0], 1)
            tf.summary.image('ground truth', label[0], 1)
            with tf.name_scope("loss"):

                _, loss, s, _, miou = sess.run([train_op, cross_entropy_loss, summ, mean_iou_update_op, meaniou_op],
                                   feed_dict={input_image: image, correct_label: label,
                                              keep_prob: 0.5, learning_rate: 1e-4})
            if train_count % 10 == 0:
                print("Epoch: {} Loss: {} mIOU:{}".format(epoch+1, loss, miou))
                writer.add_summary(s, train_count)
            train_count += 1
        meanLoss = []
        meanIOU = []
        for i in range(2):
            for image, label in get_batches_fn_valid(batch_size):
                loss, s, _, miou = sess.run([cross_entropy_loss, summ, mean_iou_update_op, meaniou_op],
                           feed_dict={input_image: image, correct_label: label,
                                      keep_prob: 1.0, learning_rate: 1e-3})
                meanLoss.append(loss)
                meanIOU.append(miou)
        print("Epoch: {} Validation Loss: {} Validation mIOU:{}".format(epoch+1,
                                            np.mean(meanLoss), np.mean(miou)))

        # if train_count % 500 == 0:
        #     saver.save(sess, os.path.join(LOGDIR, "model.ckpt"), i)

# tests.test_train_nn(train_nn)


def run():
    num_classes = 2
    image_shape = (160, 576)
    epochs = 150
    batch_size = 20
    correct_label = tf.placeholder(tf.float32, shape=(None, None, None, num_classes))
    learning_rate = tf.placeholder(tf.float32)

    data_dir = './data'
    runs_dir = './runs'
    if not os.path.exists(os.path.join(data_dir, 'data_road/training')):
        raise FileNotFoundError('Make sure you download dataset and put in data_road')
    # tests.test_for_kitti_dataset(data_dir)

    # Download pretrained vgg model
    helper.maybe_download_pretrained_vgg(data_dir)

    # OPTIONAL: Train and Inference on the cityscapes dataset instead of the Kitti dataset.
    # You'll need a GPU with at least 10 teraFLOPS to train on.
    #  https://www.cityscapes-dataset.com/


    with tf.Session() as sess:
        # Path to vgg model
        vgg_path = os.path.join(data_dir, 'vgg')
        # Create function to get batches
        get_batches_fn = helper.gen_batch_function(os.path.join(data_dir, 'data_road/training'), image_shape, train=True)
        get_batches_fn_valid = helper.gen_batch_function(os.path.join(data_dir, 'data_road/valid'), image_shape, train=False)

        # OPTIONAL: Augment Images for better results
        #  https://datascience.stackexchange.com/questions/5224/how-to-prepare-augment-images-for-neural-network
        input_image, keep_prob, layer3_out, layer4_out, layer7_out = load_vgg(sess, vgg_path)
        layer_output = layers(layer3_out, layer4_out, layer7_out, num_classes)
        logits, train_op, cross_entropy_loss, meaniou_op, mean_iou_update_op = optimize(layer_output, correct_label, learning_rate, num_classes)

        # OPTIONAL: Apply the trained model to a video
        print("Running tensorboard in {}".format(LOGDIR+"1"))

        train_nn(sess, epochs, batch_size, get_batches_fn, train_op, cross_entropy_loss, input_image,
                 correct_label, keep_prob, learning_rate, meaniou_op, mean_iou_update_op, get_batches_fn_valid)

        helper.save_inference_samples(runs_dir, data_dir, sess, image_shape, logits, keep_prob, input_image)




if __name__ == '__main__':
    run()
