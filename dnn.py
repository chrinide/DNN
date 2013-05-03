from pybrain.tools.shortcuts import buildNetwork
from pybrain.supervised.trainers import BackpropTrainer
from pybrain.datasets import SupervisedDataSet
from pybrain.structure import LinearLayer, SigmoidLayer, TanhLayer, SoftmaxLayer, BiasUnit, FeedForwardNetwork, FullConnection
import numpy
import copy

""" At this point, to use the autoencoder, you must always add one more layer into the layers argument than you actually want.
If you want 3 layers with dimensions 10,8,5 then you use layers=[10,8,5,1], where the 1 can be any number you want. This is because
the softmax layer still expects to be trained. It should eventually be moved to a different class."""

class AutoEncoder(object):

    def __init__(self, data, targets, layers=[], hidden_layer="SigmoidLayer", final_layer="SigmoidLayer", compression_epochs=100, smoothing_epochs=10, verbose=False, bias=True, autoencoding_only=True, dropout_on=True):
        self.layers = layers
        self.data = data
        self.targets = targets
        self.compression_epochs = compression_epochs
        self.smoothing_epochs = smoothing_epochs
        self.verbose = verbose
        self.bias = bias
        self.autoencoding_only = autoencoding_only
        self.nn = []
        self.dropout_on = dropout_on

        # compression layer
        if hidden_layer == "SigmoidLayer":
            self.hidden_layer = SigmoidLayer
        elif hidden_layer == "LinearLayer":
            self.hidden_layer = LinearLayer
        elif hidden_layer == "TanhLayer":
            self.hidden_layer = TanhLayer
        elif hidden_layer == "SoftmaxLayer":
            self.hidden_layer = SoftmaxLayer
        else:
            raise Exception("hidden_layer must be either: 'LinearLayer', 'SoftmaxLayer', 'SigmoidLayer', or 'TanhLayer'")

        # final layer
        if final_layer == "SigmoidLayer":
            self.final_layer = SigmoidLayer
        elif final_layer == "LinearLayer":
            self.final_layer = LinearLayer
        elif final_layer == "TanhLayer":
            self.final_layer = TanhLayer
        elif final_layer == "SoftmaxLayer":
            self.final_layer = SoftmaxLayer
        else:
            raise Exception("final_layer must be either: 'LinearLayer', 'SoftmaxLayer', 'SigmoidLayer', or 'TanhLayer'")

    def predict(self, data):
        if not self.nn: raise Exception("You must run ._train() before you can predict")
        for nn in self.nn:
            data = nn.activate(data)
        return data

    def fit(self):
        autoencoder, _, _, _ = self._train()
        autoencoder.sortModules()
        return autoencoder

    def _train(self):
        hidden_layers = []
        bias_layers = []
        compressed_data = copy.copy(self.data) # it isn't compressed at this point, but will be later on

        mid_layers = self.layers[1:-1] # remove the first and last
        for i,current in enumerate(mid_layers):
            prior = self.layers[i] # This accesses the layer before the "current" one, since the indexing in mid_layers and self.layers is offset by 1
            #print "Compressed data at stage {0} {1}".format(i, compressed_data)

            """ build the NN with a bottleneck """
            bottleneck = FeedForwardNetwork()
            in_layer = LinearLayer(prior)
            hidden_layer = self.hidden_layer(current)
            out_layer = self.hidden_layer(prior)
            bottleneck.addInputModule(in_layer)
            bottleneck.addModule(hidden_layer)
            bottleneck.addOutputModule(out_layer)
            in_to_hidden = FullConnection(in_layer, hidden_layer)
            hidden_to_out = FullConnection(hidden_layer, out_layer)
            bottleneck.addConnection(in_to_hidden)
            bottleneck.addConnection(hidden_to_out)
            if self.bias:
                bias1 = BiasUnit()
                bias2 = BiasUnit()
                bottleneck.addModule(bias1)
                bottleneck.addModule(bias2)
                bias_in = FullConnection(bias1, hidden_layer)
                bias_hidden = FullConnection(bias2, out_layer)
                bottleneck.addConnection(bias_in)
                bottleneck.addConnection(bias_hidden)
            bottleneck.sortModules()

            """ train the bottleneck """
            ds = SupervisedDataSet(prior,prior)
            if self.dropout_on:
                noisy_data = self.dropout(compressed_data)
                for i,n in enumerate(noisy_data):
                    original = compressed_data[i]
                    ds.addSample(n, original)
            else:
                for d in (compressed_data): ds.addSample(d, d)
            trainer = BackpropTrainer(bottleneck, dataset=ds, momentum=0.1, verbose=self.verbose, weightdecay=0.01)
            trainer.trainEpochs(self.compression_epochs)
            #print "ABOUT TO APPEND"
            #print in_to_hidden.params
            #print len(in_to_hidden.params)

            hidden_layers.append(in_to_hidden)
            if self.bias: bias_layers.append(bias_in)

            """ use the params from the bottleneck to compress the training data """
            compressor = FeedForwardNetwork()
            compressor.addInputModule(in_layer)
            compressor.addOutputModule(hidden_layer) # use the hidden layer from above
            compressor.addConnection(in_to_hidden)
            compressor.sortModules()
            compressed_data = [compressor.activate(d) for d in compressed_data]

            self.nn.append(compressor)
            #print "Compressed data after stage {0} {1}".format(i, compressed_data)

	    """ Train the softmax layer """
        softmax = FeedForwardNetwork()
        in_layer = LinearLayer(self.layers[-2])
        out_layer = self.final_layer(self.layers[-1])
        softmax.addInputModule(in_layer)
        softmax.addOutputModule(out_layer)
        in_to_out = FullConnection(in_layer, out_layer)
        softmax.addConnection(in_to_out)
        if self.bias:
            bias = BiasUnit()
            softmax.addModule(bias)
            bias_in = FullConnection(bias, out_layer)
            softmax.addConnection(bias_in)
        softmax.sortModules()

        ds = SupervisedDataSet(self.layers[-2], self.layers[-1])
        for i,d in enumerate(compressed_data):
            target = self.targets[i]
            ds.addSample(d, target)
        trainer = BackpropTrainer(softmax, dataset=ds, momentum=0.1, verbose=self.verbose, weightdecay=0.01)
        trainer.trainEpochs(self.compression_epochs)
        self.nn.append(softmax)
        #print "ABOUT TO APPEND"
        #print len(in_to_out.params)
        hidden_layers.append(in_to_out)
        if self.bias: bias_layers.append(bias_in)

        """ Recreate the whole thing """
        #print "hidden layers: " + str(hidden_layers)
        #print "bias layers: " + str(bias_layers)
        #print "len hidden layers: " + str(len(hidden_layers))
        #print "len bias layers: " + str(len(bias_layers))
        # connect the first two
        autoencoder = FeedForwardNetwork()
        first_layer = hidden_layers[0].inmod
        next_layer = hidden_layers[0].outmod
        autoencoder.addInputModule(first_layer)
        connection = FullConnection(first_layer, next_layer)
        connection.params[:] = hidden_layers[0].params
        autoencoder.addConnection(connection)

        # decide whether this should be the output layer or not
        if self.autoencoding_only and (len(self.layers) <= 3): # TODO change this to 2 when you aren't using the softmax above
            autoencoder.addOutputModule(next_layer)
        else:
            autoencoder.addModule(next_layer)
        if self.bias:
            bias = bias_layers[0]
            bias_unit = bias.inmod
            autoencoder.addModule(bias_unit)
            connection = FullConnection(bias_unit, next_layer)
            #print bias.params
            connection.params[:] = bias.params
            autoencoder.addConnection(connection)
            #print connection.params

        # connect the middle layers
        for i,h in enumerate(hidden_layers[1:-1]):
            new_next_layer = h.outmod

            # decide whether this should be the output layer or not
            if self.autoencoding_only and i == (len(hidden_layers) - 3):
                autoencoder.addOutputModule(new_next_layer)
            else:
                autoencoder.addModule(new_next_layer)
            connection = FullConnection(next_layer, new_next_layer)
            connection.params[:] = h.params
            autoencoder.addConnection(connection)
            next_layer = new_next_layer

            if self.bias:
                bias = bias_layers[i+1]
                bias_unit = bias.inmod
                autoencoder.addModule(bias_unit)
                connection = FullConnection(bias_unit, next_layer)
                connection.params[:] = bias.params
                autoencoder.addConnection(connection)

        return autoencoder, hidden_layers, next_layer, bias_layers

    def dropout(self, data):
        length = len(data[0])
        zeros = round(length * 0.2)
        ones = length - zeros
        zeros = numpy.zeros(zeros)
        ones = numpy.ones(ones)
        merged = numpy.concatenate((zeros, ones), axis=1)
        dropped = []
        for d in data:
            numpy.random.shuffle(merged)
            dropped.append(merged * d)
        return dropped


class DNNRegressor(AutoEncoder):

    def fit(self):
        autoencoder, hidden_layers, next_layer, bias_layers = self._train()
        return self.top_layer(autoencoder, hidden_layers, next_layer, bias_layers)

    def top_layer(self, autoencoder, hidden_layers, next_layer, bias_layers):
        # connect 2nd to last and last
        last_layer = hidden_layers[-1].outmod
        autoencoder.addOutputModule(last_layer)
        connection = FullConnection(next_layer, last_layer)
        connection.params[:] = hidden_layers[-1].params
        autoencoder.addConnection(connection)
        if self.bias:
            bias = bias_layers[-1]
            bias_unit = bias.inmod
            autoencoder.addModule(bias_unit)
            connection = FullConnection(bias_unit, last_layer)
            connection.params[:] = bias.params
            autoencoder.addConnection(connection)

        autoencoder.sortModules()
        return autoencoder

def test():
    data = []
    data.append([0,0,1,1])
    data.append([0,0,1,0.9])
    data.append([0,0,0.9,0.9])
    data.append([0.8,1,0,0])
    data.append([1,1,0.1,0])
    data.append([1,0.9,0,0.2])

    targets = []
    targets.append(0)
    targets.append(0)
    targets.append(0)
    targets.append(1)
    targets.append(1)
    targets.append(1)

    layers = [4,2,1]
    dnn = AutoEncoder(data, targets, layers, hidden_layer="TanhLayer", final_layer="TanhLayer", compression_epochs=50, smoothing_epochs=0, bias=True, autoencoding_only=True)
    #dnn = DNNRegressor(data, targets, layers, hidden_layer="TanhLayer", final_layer="TanhLayer", compression_epochs=50, smoothing_epochs=0, bias=True, autoencoding_only=False)
    dnn = dnn.fit()
    data.append([0.9, 0.8, 0, 0.1])
    print "\n-----"
    for d in data:
        print dnn.activate(d)

#test()
