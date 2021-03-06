from numpy import *
import numpy as np
import itertools
import time
import sys
import cPickle as pickle

# Import NN utils
from nn.base import NNBase
from nn.math import softmax, sigmoid, sigmoidGrad,make_onehot
from nn.math import MultinomialSampler, multinomial_sample,HierarchicalSoftmaxTree
from misc import random_weight_matrix


class RNNLM(NNBase):
    """
    Implements an RNN language model of the form:
    h(t) = sigmoid(H * h(t-1) + L[x(t)])                    #  h(t) = sigmoid(H*h(t-1) + W*L[x(t)])
    y(t) = softmax(U * h(t))
    where y(t) predicts the next word in the sequence

    U = |V| * dim(h) as output vectors                      #  lreg 
    L = |V| * dim(h) as input vectors

    You should initialize each U[i,j] and L[i,j]
    as Gaussian noise with mean 0 and variance 0.1
    For random samples from N(mu, sigma^2), use:
    sigma * np.random.randn(...) + mu

    Arguments:
        L0 : initial input word vectors
        U0 : initial output word vectors
        alpha : default learning rate
        bptt : number of backprop timesteps
    """

    def __init__(self, L0, U0=None,alpha=0.005, lreg = 0.00001, rseed=10, bptt=1):

        self.hdim = L0.shape[1] # word vector dimensions
        self.vdim = L0.shape[0] # vocab size
        param_dims = dict(H = (self.hdim, self.hdim), W = (self.hdim,self.hdim))
                          #,U = L0.shape)
        # note that only L gets sparse updates
        param_dims_sparse = dict(L = L0.shape)
        NNBase.__init__(self, param_dims, param_dims_sparse)

        self.alpha = alpha
        self.lreg = lreg
        #### YOUR CODE HERE ####
        
        # Initialize word vectors
        # either copy the passed L0 and U0 (and initialize in your notebook)
        # or initialize with gaussian noise here

        # Initialize H matrix, as with W and U in part 1
        self.bptt = bptt
        random.seed(rseed)
        self.params.H = random_weight_matrix(*self.params.H.shape)
        self.params.W = random_weight_matrix(*self.params.W.shape)
        #self.params.U = 0.1*np.random.randn(*L0.shape)
        self.sparams.L = L0.copy()
        #### END YOUR CODE ####


    def _acc_grads(self, xs, ys):
        """
        Accumulate gradients, given a pair of training sequences:
        xs = [<indices>] # input words
        ys = [<indices>] # output words (to predict)

        Your code should update self.grads and self.sgrads,
        in order for gradient_check and training to work.

        So, for example:
        self.grads.H += (your gradient dJ/dH)
        self.sgrads.L[i] = (gradient dJ/dL[i]) # update row

        Per the handout, you should:
            - make predictions by running forward in time
                through the entire input sequence
            - for *each* output word in ys, compute the
                gradients with respect to the cross-entropy
                loss for that output word
            - run backpropagation-through-time for self.bptt
                timesteps, storing grads in self.grads (for H, U)
                and self.sgrads (for L)

        You'll want to store your predictions \hat{y}(t)
        and the hidden layer values h(t) as you run forward,
        so that you can access them during backpropagation.
        
        At time 0, you should initialize the hidden layer to
        be a vector of zeros.
        """

        # Expect xs as list of indices
        ns = len(xs)

        # make matrix here of corresponding h(t)
        # hs[-1] = initial hidden state (zeros)
        hs = np.zeros((ns+1, self.hdim))
        # predicted probas
        ps = np.zeros((ns+1, self.vdim))

        #### YOUR CODE HERE ####
        ##
        # Forward propagation

        zs = np.zeros((ns+1,self.hdim))
        for i in range(ns):
            zs[i+1] = self.params.H.dot(hs[i]) + self.params.W.dot(self.sparams.L[xs[i]])
            hs[i+1] = sigmoid(zs[i+1])
            ps[i+1] = softmax(self.params.U.dot(hs[i+1]))
        ##
        # Backward propagation through time
        sgradsTmp = np.zeros((self.vdim,self.hdim)) 
        grad0 = np.zeros((ns+1,self.hdim)) # (y-t)*U 
        for i in range(ns):
            grad0[i+1] = (ps[i+1]-make_onehot(ys[i],self.vdim)).dot(self.params.U)
            self.grads.U += np.outer((ps[i+1]-make_onehot(ys[i],self.vdim)),hs[i+1])
            vectorCurrent = grad0[i+1]*sigmoidGrad(zs[i+1])
            for j in range(min(i+1,self.bptt+1)):
                xh1 = np.ones((self.hdim, self.hdim)).dot(np.diag(hs[i-j]))
                self.grads.H += np.diag(vectorCurrent).dot(xh1)
                x1 = np.ones((self.hdim, self.hdim)).dot(np.diag(self.sparams.L[xs[i-j]]))
                self.grads.W += np.diag(vectorCurrent).dot(x1)
                sgradsTmp[xs[i-j]] += vectorCurrent.dot(self.params.W)
                
                vectorCurrent = vectorCurrent.dot(self.params.H)
                vectorCurrent = vectorCurrent*sigmoidGrad(zs[i-j])

        self.grads.U += self.lreg*self.params.U
        self.grads.H += self.lreg*self.params.H
        self.grads.W += self.lreg*self.params.W
        
        for i in range(len(sgradsTmp)):
            self.sgrads.L[i] = sgradsTmp[i,:]
        #### END YOUR CODE ####


    def grad_check(self, x, y, outfd=sys.stderr, **kwargs):
        """
        Wrapper for gradient check on RNNs;
        ensures that backprop-through-time is run to completion,
        computing the full gradient for the loss as summed over
        the input sequence and predictions.

        Do not modify this function!
        """
        bptt_old = self.bptt
        self.bptt = len(y)
        print >> outfd, "NOTE: temporarily setting self.bptt = len(y) = %d to compute true gradient." % self.bptt
        NNBase.grad_check(self, x, y, outfd=outfd, **kwargs)
        self.bptt = bptt_old
        print >> outfd, "Reset self.bptt = %d" % self.bptt


    def compute_seq_loss(self, xs, ys):
        """
        Compute the total cross-entropy loss
        for an input sequence xs and output
        sequence (labels) ys.

        You should run the RNN forward,
        compute cross-entropy loss at each timestep,
        and return the sum of the point losses.
        """

        J = 0
        #### YOUR CODE HERE ####
        ns = len(xs)
        hs = np.zeros((ns+1,self.hdim))
        for i in range(ns):
            hs[i+1] = sigmoid(self.params.H.dot(hs[i])+self.params.W.dot(self.sparams.L[xs[i]]))
            p = softmax(self.params.U.dot(hs[i+1]))
            p = p*make_onehot(ys[i],self.vdim)
            J += -np.log(np.sum(p))
        #### END YOUR CODE ####

        Jreg = 0.5*self.lreg*(np.sum(self.params.H**2)+np.sum(self.params.W**2)+np.sum(self.params.U**2))
        return J + Jreg


    def compute_loss(self, X, Y):
        """
        Compute total loss over a dataset.
        (wrapper for compute_seq_loss)

        Do not modify this function!
        """
        if not isinstance(X[0], ndarray): # single example
            return self.compute_seq_loss(X, Y)
        else: # multiple examples
            return sum([self.compute_seq_loss(xs,ys)
                       for xs,ys in itertools.izip(X, Y)])

    def compute_mean_loss(self, X, Y):
        """
        Normalize loss by total number of points.

        Do not modify this function!
        """
        J = self.compute_loss(X, Y)
        ntot = sum(map(len,Y))
        return J / float(ntot)


    def generate_sequence(self, init, end, maxlen=100):
        """
        Generate a sequence from the language model,
        by running the RNN forward and selecting,
        at each timestep, a random word from the
        a word from the emitted probability distribution.

        The MultinomialSampler class (in nn.math) may be helpful
        here for sampling a word. Use as:

            y = multinomial_sample(p)

        to sample an index y from the vector of probabilities p.


        Arguments:
            init = index of start word (word_to_num['<s>'])
            end = index of end word (word_to_num['</s>'])
            maxlen = maximum length to generate

        Returns:
            ys = sequence of indices
            J = total cross-entropy loss of generated sequence
        """
        J = 0 # total loss
        ys = [init] # emitted sequence

        ns = maxlen
        hs = np.zeros((ns+1,self.hdim))
        #### YOUR CODE HERE ####
        for i in range(ns):
            hs[i+1] = sigmoid(self.params.H.dot(hs[i])+self.params.W.dot(self.sparams.L[ys[i]]))
            p = softmax(self.params.U.dot(hs[i+1]))
            y = multinomial_sample(p)
            ys.append(y)
            if y == end:
                break
            p = p*make_onehot(y,self.vdim)
            J += -np.log(np.sum(p))
            
        Jreg = 0.5*self.lreg*(np.sum(self.params.H**2)+np.sum(self.params.W**2)+np.sum(self.params.U**2))
        #### YOUR CODE HERE ####
        return ys, J+Jreg



class ExtensionRNNLM(RNNLM):
    """
    Implements an improved RNN language model,
    for better speed and/or performance.

    We're not going to place any constraints on you
    for this part, but we do recommend that you still
    use the starter code (NNBase) framework that
    you've been using for the NER and RNNLM models.
    """
    
    def __init__(self, L0, U0=None,alpha=0.005, lreg = 0.00001, rseed=10, bptt=1):
        #### YOUR CODE HERE ####
        
        RNNLM.__init__(self,L0,alpha,lreg,rseed,bptt)
        self.word2node = {}
        self.hierarchicalU = HierarchicalSoftmaxTree(L0.shape[0],L0.shape[1],self.word2node)

        #print self.params.names()
        #raise NotImplementedError("__init__() not yet implemented.")
        #### END YOUR CODE ####
          
    def _acc_grads(self, xs, ys):
        #### YOUR CODE HERE ####
        # Expect xs as list of indices
        ns = len(xs)
        # make matrix here of corresponding h(t)
        # hs[-1] = initial hidden state (zeros)
        hs = np.zeros((ns+1, self.hdim))
        # predicted probas
        ps = np.zeros((ns+1, self.vdim))

        #### YOUR CODE HERE ####
        ##
        # Forward propagation

        zs = np.zeros((ns+1,self.hdim))
        for i in range(ns):
            zs[i+1] = self.params.H.dot(hs[i]) + self.params.W.dot(self.sparams.L[xs[i]])
            hs[i+1] = sigmoid(zs[i+1])
            
        ##
        # Backward propagation through time
        sgradsTmp = np.zeros((self.vdim,self.hdim)) 
        grad0 = np.zeros((ns+1,self.hdim)) # (y-t)*U 
        for i in range(ns):
            nodeCur = self.word2node[ys[i]]
            while nodeCur.parent != None:
                t = 1
                if nodeCur.isLeft == False:
                    t = 0
                nodeCur = nodeCur.parent
                if nodeCur.grad == None:
                    nodeCur.grad = (sigmoid(nodeCur.hActs.dot(hs[i+1]))-t)*hs[i+1]
                else:
                    nodeCur.grad = nodeCur.grad + (sigmoid(nodeCur.hActs.dot(hs[i+1]))-t)*hs[i+1]
                    
                grad0[i+1] = grad0[i+1] + (sigmoid(nodeCur.hActs.dot(hs[i+1]))-t)*nodeCur.hActs

                    
            vectorCurrent = grad0[i+1]*sigmoidGrad(zs[i+1])
            for j in range(min(i+1,self.bptt+1)):
                xh1 = np.ones((self.hdim, self.hdim)).dot(np.diag(hs[i-j]))
                self.grads.H += np.diag(vectorCurrent).dot(xh1)
                x1 = np.ones((self.hdim, self.hdim)).dot(np.diag(self.sparams.L[xs[i-j]]))
                self.grads.W += np.diag(vectorCurrent).dot(x1)
                sgradsTmp[xs[i-j]] += vectorCurrent.dot(self.params.W)
                
                vectorCurrent = vectorCurrent.dot(self.params.H)
                vectorCurrent = vectorCurrent*sigmoidGrad(zs[i-j])

        
        self.hierarchicalU.regularizedGrad(self.hierarchicalU.root,self.lreg)
        self.grads.H += self.lreg*self.params.H
        self.grads.W += self.lreg*self.params.W
        
        for i in range(len(sgradsTmp)):
            self.sgrads.L[i] = sgradsTmp[i,:]
        #### END YOUR CODE ####




    def _acc_grads1(self, xs, ys):
        #### YOUR CODE HERE ####
        # Expect xs as list of indices
        ns = len(xs)
        # make matrix here of corresponding h(t)
        # hs[-1] = initial hidden state (zeros)
        hs = np.zeros((ns+1, self.hdim))
        # predicted probas
        ps = np.zeros((ns+1, self.vdim))

        #### YOUR CODE HERE ####
        ##
        # Forward propagation

        zs = np.zeros((ns+1,self.hdim))
        for i in range(ns):
            zs[i+1] = self.params.H.dot(hs[i]) + self.params.W.dot(self.sparams.L[xs[i]])
            hs[i+1] = sigmoid(zs[i+1])
            
        ##
        # Backward propagation through time
        sgradsTmp = np.zeros((self.vdim,self.hdim)) 
        grad0 = np.zeros((ns+1,self.hdim)) # (y-t)*U 
        for i in range(ns):
            nodeCur = self.word2node[ys[i]]
            while nodeCur.parent != None:
                t = 1
                if nodeCur.isLeft == False:
                    t = 0
                nodeCur = nodeCur.parent
                if nodeCur.grad == None:
                    nodeCur.grad = (sigmoid(nodeCur.hActs.dot(hs[i+1]))-t)*hs[i+1]
                else:
                    nodeCur.grad = nodeCur.grad + (sigmoid(nodeCur.hActs.dot(hs[i+1]))-t)*hs[i+1]
                grad0[i+1] = grad0[i+1] + (sigmoid(nodeCur.hActs.dot(hs[i+1]))-t)*nodeCur.hActs
                
            vectorCurrent = grad0[i+1]*sigmoidGrad(zs[i+1])
            for j in range(min(i+1,self.bptt+1)):
                xh1 = np.ones((self.hdim, self.hdim)).dot(np.diag(hs[i-j]))
                self.grads.H += np.diag(vectorCurrent).dot(xh1)
                x1 = np.ones((self.hdim, self.hdim)).dot(np.diag(self.sparams.L[xs[i-j]]))
                self.grads.W += np.diag(vectorCurrent).dot(x1)
                sgradsTmp[xs[i-j]] += vectorCurrent.dot(self.params.W)
                
                vectorCurrent = vectorCurrent.dot(self.params.H)
                vectorCurrent = vectorCurrent*sigmoidGrad(zs[i-j])

        
        self.hierarchicalU.regularizedGrad(self.hierarchicalU.root,self.lreg)
        self.grads.H += self.lreg*self.params.H
        self.grads.W += self.lreg*self.params.W
        
        for i in range(len(sgradsTmp)):
            self.sgrads.L[i] = sgradsTmp[i,:]
        #### END YOUR CODE ####
        
    def compute_seq_loss(self, xs, ys):
        """
        Compute the total cross-entropy loss
        for an input sequence xs and output
        sequence (labels) ys.

        You should run the RNN forward,
        compute cross-entropy loss at each timestep,
        and return the sum of the point losses.
        """

        J = 0
        #### YOUR CODE HERE ####
        ns = len(xs)
        hs = np.zeros((ns+1,self.hdim))
        for i in range(ns):
            hs[i+1] = sigmoid(self.params.H.dot(hs[i])+self.params.W.dot(self.sparams.L[xs[i]]))
            nodeCur = self.word2node[ys[i]]
            while nodeCur.parent != None:
                t = 1
                if nodeCur.isLeft == False:
                    t = -1
                nodeCur = nodeCur.parent
                J += -np.log(sigmoid(t*nodeCur.hActs.dot(hs[i+1])))
        #### END YOUR CODE ####
        x = self.hierarchicalU.getSumSquareU(self.hierarchicalU.root)
        Jreg = 0.5*self.lreg*(np.sum(self.params.H**2)+np.sum(self.params.W**2) + x)
        return J + Jreg

    def generate_sequence(self, init, end, maxlen=100):
        """
        Generate a sequence from the language model,
        by running the RNN forward and selecting,
        at each timestep, a random word from the
        a word from the emitted probability distribution.

        The MultinomialSampler class (in nn.math) may be helpful
        here for sampling a word. Use as:

            y = multinomial_sample(p)

        to sample an index y from the vector of probabilities p.


        Arguments:
            init = index of start word (word_to_num['<s>'])
            end = index of end word (word_to_num['</s>'])
            maxlen = maximum length to generate

        Returns:
            ys = sequence of indices
            J = total cross-entropy loss of generated sequence
        """
        J = 0 # total loss
        ys = [init] # emitted sequence

        ns = maxlen
        hs = np.zeros((ns+1,self.hdim))
        #### YOUR CODE HERE ####
        for i in range(ns):
            hs[i+1] = sigmoid(self.params.H.dot(hs[i])+self.params.W.dot(self.sparams.L[ys[i]]))            
            p = self.hierarchicalU.getDistribution(hs[i+1])
            y = multinomial_sample(p)
            ys.append(y)
            if y == end:
                break
            p = p*make_onehot(y,self.vdim)
            J += -np.log(np.sum(p))


        ##
        #x only compute the node which gradient is updated 
        x = self.hierarchicalU.getSumSquareU(self.hierarchicalU.root)
        Jreg = 0.5*self.lreg*(np.sum(self.params.H**2)+np.sum(self.params.W**2)+ x)
        #### YOUR CODE HERE ####
        return ys, J+Jreg

####################################################
#in order to reimplement train_sgd()
#we reimplement _reset_grad_acc() and _apply_grad_acc(),
#thus train_point/minibatch_sgd()

    def _reset_grad_acc(self):
        """Reset accumulated gradients."""
        self.grads.reset()
        self.sgrads.reset()
        self.hierarchicalU.reset(self.hierarchicalU.root)
        
    def _apply_grad_acc(self, alpha=1.0):
        """
        Update parameters with accumulated gradients.

        alpha can be a scalar (as in SGD), or a vector
        of the same length as the full concatenated
        parameter vector (as in e.g. AdaGrad)
        """
        # Dense updates
        self.params.full -= alpha * self.grads.full
        # Sparse updates
        self.sgrads.apply_to(self.sparams, alpha=-1*alpha)
        # hierarchical softmax U
        self.hierarchicalU.apply_grad_acc(self.hierarchicalU.root, alpha=-1*alpha)        

########################################################
    #we need this grad_check ,because although the member variable
    #defined
    #in Class ExtensionRNNLM (hierarchicalU) can be accessed in Class
    #NNBase method(grad_check) as long as this object variable is
    #exclaimed as ExtensionRNNLM
    #if you define a object variable exclaimed as RNNLM, it will come
    #error

    def grad_check_hierarchicalU(self,node,grad_computed,grad_approx,eps,x,y):
        if node.isLeaf == True:
            return
        if node.grad == None:
            return

        theta = node.hActs
        for ij,v in np.ndenumerate(node.hActs):
            tij = theta[ij]
            theta[ij] = tij + eps
            Jplus = self.compute_loss(x,y)
            theta[ij] = tij - eps
            Jminus = self.compute_loss(x, y)
            theta[ij] = tij # reset
            approx = (Jplus - Jminus)/(2*eps)
            grad_computed.append(node.grad[ij])
            grad_approx.append(approx)

        self.grad_check_hierarchicalU(node.left,grad_computed,grad_approx,eps,x,y)
        self.grad_check_hierarchicalU(node.right,grad_computed,grad_approx,eps,x,y)
        
            
    def grad_check(self, x, y, eps=1e-4, tol=1e-6,
                   outfd=sys.stderr, verbose=False,
                   skiplist=[]):
        """
        Generic gradient check: uses current params
        aonround a specific data point (x,y)

        This is implemented for diagnostic purposes,
        and is not optimized for speed. It is recommended
        to run this on a couple points to test a new
        neural network implementation.
        """
        # Accumulate gradients in self.grads
        # print "reset_grad "
        self._reset_grad_acc()
        # print "acc_grad "
        self._acc_grads(x, y)  # include H,W,and hierarchicalU
        # print "sgrad "
        t1 = time.time()
        self.sgrads.coalesce() #combine sparse updates
        t2 = time.time()

        print "sgrad finished .. time is %f" %(t2-t1)
        ##
        # Loop over dense parameters
        for name in self.params.names():
            if name in skiplist: continue
            theta = self.params[name]
            grad_computed = self.grads[name]
            grad_approx = np.zeros(theta.shape)
            for ij, v in np.ndenumerate(theta):
                tij = theta[ij]
                theta[ij] = tij + eps
                Jplus  = self.compute_loss(x, y)
                theta[ij] = tij - eps
                Jminus = self.compute_loss(x, y)
                theta[ij] = tij # reset

                grad_approx[ij] = (Jplus - Jminus)/(2*eps)
            # Compute Frobenius norm
            grad_delta = linalg.norm(grad_approx - grad_computed)
            print >> outfd, "grad_check: dJ/d%s error norm = %.04g" % (name, grad_delta),
            print >> outfd, ("[ok]" if grad_delta < tol else "**ERROR**")
            print >> outfd, "    %s dims: %s = %d elem" % (name, str(list(theta.shape)), prod(theta.shape))
            if verbose and (grad_delta > tol): # DEBUG
                print >> outfd, "Numerical: \n" + str(grad_approx)
                print >> outfd, "Computed:  \n" + str(grad_computed)


        t3 = time.time()
        # print "grad check on H and W , time %f" %(t3-t2)
        ##
        #Traverse over hierarchical softmax U
        grad_computed = []
        grad_approx = []
        name = "softmaxU"
        self.grad_check_hierarchicalU(self.hierarchicalU.root,grad_computed,grad_approx,eps,x,y)
        grad_computed = np.array(grad_computed)
        grad_approx = np.array(grad_approx)
        grad_delta = linalg.norm(grad_approx - grad_computed)
        print >> outfd, "grad_check: dJ/d%s error norm = %.04g" % (name, grad_delta),
        print >> outfd, ("[ok]" if grad_delta < tol else "**ERROR**")
        #print >> outfd, "    %s dims: %s = %d elem" % (name, str(list(theta.shape)), prod(theta.shape))
        if verbose and (grad_delta > tol): # DEBUG
            print >> outfd, "Numerical: \n" + str(grad_approx)
            print >> outfd, "Computed:  \n" + str(grad_computed)
        

        t4 = time.time()
        print "grad check on Hierarchical U , time is %f" %(t4-t3)
        ##
        # Loop over sparse parameters
        for name in self.sparams.names():
            if name in skiplist: continue
            theta_full = self.sparams[name]
            idxblocks = np.indices(theta_full.shape)
            # Loop over all sparse updates for this parameter
            for idx, grad_computed in self.sgrads[name]:
                # For arbitary indexing, might not get a contiguous block
                # therefore, can't use views for aliasing here
                # Solution: generate index arrays, select indices
                # then use these for sparse grad check
                idxtuples = zip(*[d[idx].flat for d in idxblocks])
                grad_approx = zeros(len(idxtuples))
                theta = theta_full # alias full
                for k, ij in enumerate(idxtuples):
                    tij = theta[ij]
                    theta[ij] = tij + eps
                    Jplus  = self.compute_loss(x, y)
                    theta[ij] = tij - eps
                    Jminus = self.compute_loss(x, y)
                    theta[ij] = tij # reset
                    grad_approx[k] = (Jplus - Jminus)/(2*eps)
                    
                grad_approx = grad_approx.reshape(grad_computed.shape)
                grad_delta = linalg.norm(grad_approx - grad_computed)
                print >> outfd, "grad_check: dJ/d%s[%s] error norm = %.04g" % (name, idx, grad_delta),
                print >> outfd, ("[ok]" if grad_delta < tol else "**ERROR**")
                print >> outfd, "    %s[%s] dims: %s = %d elem" % (name, idx, str(list(grad_computed.shape)), prod(grad_computed.shape))

                #verbose = True
                if verbose and (grad_delta > tol): # DEBUG
                    print >> outfd, "Numerical: \n" + str(grad_approx)
                    print >> outfd, "Computed:  \n" + str(grad_computed)


        t5 = time.time()
        print "grad check on word vector , time is %f" %(t5-t4)
        self._reset_grad_acc()




def save_params(filename,params):
    with open(filename,"w") as f:
        pickle.dump(params,f)


def seq_to_words(seq):
    return [num_to_word[s] for s in seq]

def adjust_loss(loss, funk, q, mode='basic'):
    if mode == 'basic':
        return (loss + funk*log(funk))/(1-funk)
    else:
        return loss + funk*log(funk)-funk*log(q)

def fill_unknowns(words,vocab):
    ret = words
    p = np.array([freq for word, freq in dict(vocab["freq"]).items()])
    #print "summize all probability -> ",np.sum(p)
    for i in range(len(words)):
        if words[i] == "UUUNKKK":
            ret[i] = vocab.index[multinomial_sample(p)]
        else:
            ret[i] = words[i]
    return ret


def Generator(y_train):
    nepoch = 5
    N = nepoch*len(y_train)
    k = 8
    random.seed(10)
    for i in range(N):
        yield np.random.randint(0,len(y_train),k)


if __name__ == "__main__":
    random.seed(10)
    wv_dummy = random.randn(10,20)
    model = ExtensionRNNLM(L0 = wv_dummy, U0=wv_dummy,alpha=0.005,lreg=0.000001,rseed=10,bptt=4)
    model.grad_check(np.array([0,1,2,3,4]),np.array([1,2,3,4,5]))

    
    from data_utils import utils as du
    import pandas as pd

    vocab = pd.read_table("data/lm/vocab.ptb.txt",header=None, sep="\s+", index_col=0, names=['count','freq'])
    vocabsize = len(vocab)
    num_to_word = dict(enumerate(vocab.index[:vocabsize]))
    word_to_num = du.invert_dict(num_to_word)

    fraction_lost = float(sum([vocab['count'][word] for word in vocab.index
                               if (not word in word_to_num) and
                               (not word == "UUUNKKK")]))
    fraction_lost /= sum([vocab['count'][word] for word in vocab.index
                          if (not word == "UUUNKKK")])

    print "Retained %d words from %d (%.02f%% of all tokens)" %(vocabsize,len(vocab),100*(1-fraction_lost))

    docs = du.load_dataset('data/lm/ptb-train.txt')
    S_train = du.docs_to_indices(docs, word_to_num)
    X_train, Y_train = du.seqs_to_lmXY(S_train)
    
    docs = du.load_dataset('data/lm/ptb-dev.txt')
    S_dev = du.docs_to_indices(docs, word_to_num)
    X_dev, Y_dev = du.seqs_to_lmXY(S_dev)
    
    docs = du.load_dataset('data/lm/ptb-test.txt')
    S_test = du.docs_to_indices(docs,word_to_num)
    X_test, Y_test = du.seqs_to_lmXY(S_test)

    #For random samples from N(mu, sigma^2), use:
    #    sigma * np.random.randn(...) + mu

    
    hdim = 20
    random.seed(10)
    L0 = 0.1*np.random.randn(vocabsize,hdim) 
    model = ExtensionRNNLM(L0, U0=L0, alpha=0.1, rseed=10, bptt=3)
    #model.grad_check(np.array([1,2,3,4]),np.array([2,3,4,5]))

    idxiter = Generator(Y_train)
    # trainCost = model.train_sgd(X_train, Y_train, idxiter)

    # save_params("rnnlmWithWExention.L.npy", model.sparams.L)
    # save_params("rnnlmWithWExention.U.npy", model.params.U)
    # save_params("rnnlmWithWExention.W.npy", model.params.W)
    # save_params("rnnlmWithWExention.H.npy", model.params.H)


    # for i in range(10):
    #     seq, J = model.generate_sequence(word_to_num["<s>"],word_to_num["</s>"],maxlen=100)
    #     print J
    #     #print " ".join(seq_to_words(seq))
    #     print " ".join(fill_unknowns(seq_to_words(seq),vocab))
    
    # dev_loss = model.compute_mean_loss(X_dev, Y_dev)
    # q = vocab.freq[vocabsize]/np.sum(vocab.freq[vocabsize:])
    # print "Unadjusted: %.03f" % np.exp(dev_loss)
    # print "Adjusted for missing vocab: %.03f" % np.exp(adjust_loss(dev_loss,fraction_lost,q))

    
    
    
