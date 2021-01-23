from classifip.dataset.arff import ArffFile
from classifip.representations.voting import Scores
from classifip.models.mlc.mlcncc import MLCNCC
from classifip.models.qda import NaiveDiscriminant, EuclideanDiscriminant, \
    LinearDiscriminant, QuadraticDiscriminant, __factory_igda_model
from classifip.models.qda_precise import NaiveDiscriminantPrecise, \
    EuclideanDiscriminantPrecise, LinearDiscriminantPrecise, \
    QuadraticDiscriminantPrecise, __factory_gda_precise
import numpy as np
from math import exp


class IGDA_BR(MLCNCC):
    """
        Gaussian discriminant analysis for binary relevance

        - It is mandatory that data is normalised (scaling feature)
        for using an imprecise parameter to values c = {0, 0.5, 1, 1.5, 2.0}
    """

    def __init__(self,
                 solver_matlab=False,
                 gda_method="nda",
                 add_path_matlab=None,
                 DEBUG=False):
        """
        :param solver_matlab: If it is
            true: it create a only classifier to handle m-binary classifier (exact solver matlab)
            false: it create a classifier by binary classifier (approximation solver python)
        :param gda_method: inda, ieda, ilda, iqda
        :param add_path_matlab:
        :param DEBUG:
        """
        super(IGDA_BR, self).__init__(DEBUG)
        self.nda_models = None
        self.nb_feature = None
        self.__solver_matlab = solver_matlab
        self.__igda_name = "i" + gda_method
        self.__gda_name = gda_method
        self._logger = create_logger("IGDA_BR", DEBUG)
        if self.__solver_matlab:
            self._nda_imprecise = __factory_igda_model(model_type=self.__igda_name,
                                                       solver_matlab=True,
                                                       add_path_matlab=add_path_matlab,
                                                       DEBUG=DEBUG)

    def learn(self,
              learn_data_set,
              nb_labels,
              ell_imprecision=0.5):
        self.__init__()

        self.nb_labels = nb_labels
        self.training_size = len(learn_data_set.data)
        self.label_names = learn_data_set.attributes[-self.nb_labels:]
        self.feature_names = learn_data_set.attributes[:-self.nb_labels]
        self.nb_feature = len(self.feature_names)
        # create the naive discriminant models
        self.nda_models = dict()
        _np_data = np.array(learn_data_set.data)
        for label_value in self.label_names:
            label_index = learn_data_set.attributes.index(label_value)
            X_learning, y_learning = list(), list()
            for row_index, raw_instance in enumerate(learn_data_set.data):
                if raw_instance[label_index] != '-1':
                    X_learning.append(_np_data[row_index, :self.nb_feature])
                    y_learning.append(_np_data[row_index, label_index])
            X_learning = np.array(X_learning, dtype=np.float)
            y_learning = np.array(y_learning)

            if not self.__solver_matlab:
                nda_imprecise = __factory_igda_model(model_type=self.__igda_name,
                                                     solver_matlab=False,
                                                     add_path_matlab=None,
                                                     DEBUG=self.DEBUG)
                nda_imprecise.learn(X=X_learning, y=y_learning, ell=ell_imprecision)
            else:
                nda_imprecise = dict({'X': X_learning,
                                      'y': y_learning,
                                      'ell': ell_imprecision})
            nda_precise = __factory_model_precise(model_type=self.__gda_name)
            nda_precise.learn(X=X_learning, y=y_learning)
            self.nda_models[label_value] = dict({
                "imprecise": nda_imprecise,
                "precise": nda_precise
            })

    def evaluate(self, test_dataset, **kwargs):
        answers = []
        for instance in test_dataset:
            # validate instance is np-array
            instance = np.array(instance)
            if len(instance) > self.nb_feature:
                instance = np.array(instance[:self.nb_feature], dtype=float)
            else:
                instance = instance.astype(dtype=float)

            skeptic = [None] * self.nb_labels
            precise = [None] * self.nb_labels
            precise_proba = [None] * self.nb_labels
            for i, label_value in enumerate(self.label_names):
                models = self.nda_models[label_value]
                # imprecise classifier
                if self.__solver_matlab:
                    self._nda_imprecise.learn(X=models["imprecise"]["X"],
                                              y=models["imprecise"]["y"],
                                              ell=models["imprecise"]["ell"])
                    i_classifier = self._nda_imprecise
                else:
                    i_classifier = models["imprecise"]

                # imprecise binary inference
                evaluate = i_classifier.evaluate(query=instance)
                skeptic[i] = -1 if len(evaluate) > 1 else int(evaluate[0])

                # precise binary inference
                evaluate, probabilities = models["precise"].evaluate(queries=[instance],
                                                                     with_posterior=True)
                precise[i] = int(evaluate[0])
                precise_proba[i] = probabilities

                # Print to verify in precise probability is in credal set
                if self.DEBUG:
                    __print_probability_intervals(i_classifier)

            answers.append((skeptic, precise, precise_proba))
        return answers

    def __print_probability_intervals(self, i_classifier):
        bounds_X_cond_Y = i_classifier.get_bound_cond_probability()
        lower_cond_0 = bounds_X_cond_Y['0']['inf'][0]
        upper_cond_0 = bounds_X_cond_Y['0']['sup'][0]
        upper_cond_1 = bounds_X_cond_Y['1']['sup'][0]
        lower_cond_1 = None
        if 'inf' in bounds_X_cond_Y['1']:
            lower_cond_1 = bounds_X_cond_Y['1']['inf'][0]

        self._logger.debug("Conditional probability of %s:0 "
                           "is [%s, %s] and  %s:1 is [%s, %s]",
                           label_value, lower_cond_0, upper_cond_0,
                           label_value, lower_cond_1, upper_cond_1)

        marginal_Y = i_classifier.get_marginal_probabilities()
        lower_0 = lower_cond_0 * marginal_Y['0'] / (
                lower_cond_0 * marginal_Y['0'] + upper_cond_1 * marginal_Y['1'])
        upper_1 = upper_cond_1 * marginal_Y['1'] / (
                upper_cond_1 * marginal_Y['1'] + lower_cond_0 * marginal_Y['0'])
        upper_0, lower_1 = None, None
        if lower_cond_1 is not None:
            lower_1 = lower_cond_1 * marginal_Y['1'] / (
                    lower_cond_1 * marginal_Y['1'] + upper_cond_0 * marginal_Y['0'])
            upper_0 = 1 - lower_1

        self._logger.debug("Interval probability of %s:0 is [%s, %s] ",
                           label_value, lower_0, upper_0)
        self._logger.debug("Interval probability of %s:1 is [%s, %s] ",
                           label_value, lower_1, upper_1)
        self._logger.debug("Precise probability of %s is [%s, %s] ",
                           label_value, probabilities[0], probabilities[1])
