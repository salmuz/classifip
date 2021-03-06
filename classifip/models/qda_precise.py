import random, numpy as np, pandas as pd, sys
from numpy import linalg
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis, \
    QuadraticDiscriminantAnalysis


class BaseEstimator:
    def __init__(self):
        self._data, self._N, self._p = None, 0, 0
        self._clazz, self._nb_clazz = None, None
        self._means, self._prior = dict(), dict()
        self._icov, self._dcov = dict(), dict()

    def learn(self, X, y):
        self._N, self._p = X.shape
        self._data = pd.concat([pd.DataFrame(X, dtype="float64"), pd.Series(y, dtype="category")], axis=1)
        columns = ["x" + i for i in map(str, range(self._p))]
        columns.extend('y')
        self._data.columns = columns
        self._clazz = np.array(self._data.y.cat.categories.tolist())
        self._nb_clazz = len(self._clazz)

    def pdf(self, query, mean, inv_cov, det_cov):
        _exp = -0.5 * ((query - mean).T @ inv_cov @ (query - mean))
        _const = np.power(det_cov, -0.5) / np.power(2 * np.pi, self._p / 2)
        return _const * np.exp(_exp)

    def evaluate(self, queries, with_posterior=False):
        predict_clazz = list()
        probabilities_query = list()
        for query in queries:
            pbs = np.array([
                self.pdf(query, self._means[clazz], self._icov[clazz], self._dcov[clazz]) *
                self._prior[clazz] for clazz in self._clazz
            ])
            predict_clazz.append(self._clazz[pbs.argmax()])
            sum_pbs = np.sum(pbs)
            probabilities_query.append([pbs[i] / sum_pbs for i in range(len(self._clazz))])
        if with_posterior:
            return predict_clazz, probabilities_query
        else:
            return predict_clazz


class LinearDiscriminantPrecise(BaseEstimator):

    def __init__(self, **kwargs):
        super(LinearDiscriminantPrecise, self).__init__()
        self.__wrapped_model = LinearDiscriminantAnalysis(**kwargs)

    def learn(self, X, y):
        self.__wrapped_model.fit(X, y)

    def evaluate(self, queries, with_posterior=False):
        predict_clazz = self.__wrapped_model.predict(queries)
        probabilities_query = self.__wrapped_model.predict_proba(queries)
        if with_posterior:
            return predict_clazz, probabilities_query
        else:
            return predict_clazz


class QuadraticDiscriminantPrecise(BaseEstimator):
    def __init__(self, **kwargs):
        super(QuadraticDiscriminantPrecise, self).__init__()
        self.__wrapped_model = QuadraticDiscriminantAnalysis(**kwargs)

    def learn(self, X, y):
        self.__wrapped_model.fit(X, y)

    def evaluate(self, queries, with_posterior=False):
        predict_clazz = self.__wrapped_model.predict(queries)
        probabilities_query = self.__wrapped_model.predict_proba(queries)
        if with_posterior:
            return predict_clazz, probabilities_query
        else:
            return predict_clazz


class EuclideanDiscriminantPrecise(BaseEstimator):

    def learn(self, X, y):
        super(EuclideanDiscriminantPrecise, self).learn(X, y)
        for clazz in self._clazz:
            self._means[clazz] = self._data[self._data.y == clazz].iloc[:, :-1].mean().as_matrix()
            self._prior[clazz] = len(self._data[self._data.y == clazz]) / self._N
            self._icov[clazz] = np.identity(self._p)
            self._dcov[clazz] = 1


class NaiveDiscriminantPrecise(BaseEstimator):
    """
        Similar to classifier: sklearn.naive_bayes.GaussianNB (verified)
    """

    def learn(self, X, y):
        super(NaiveDiscriminantPrecise, self).learn(X, y)
        # cov_total = np.diag(np.var(self._data.iloc[:, :-1])) # Naive with variance global
        for clazz in self._clazz:
            self._means[clazz] = self._data[self._data.y == clazz].iloc[:, :-1].mean().values
            self._prior[clazz] = len(self._data[self._data.y == clazz]) / self._N
            cov_clazz = np.diag(np.var(self._data[self._data.y == clazz].iloc[:, :-1]))
            if linalg.cond(cov_clazz) < 1 / sys.float_info.epsilon:
                self._icov[clazz] = linalg.inv(cov_clazz)
                self._dcov[clazz] = linalg.det(cov_clazz)
            else:  # computing pseudo inverse/determinant to a singular covariance matrix
                self._icov[clazz] = linalg.pinv(cov_clazz)
                eig_values, _ = linalg.eig(cov_clazz)
                self._dcov[clazz] = np.product(eig_values[(eig_values > 1e-12)])


MODEL_TYPES_PRECISE = {'lda': LinearDiscriminantPrecise, 'qda': QuadraticDiscriminantPrecise,
                       'eda': EuclideanDiscriminantPrecise, 'nda': NaiveDiscriminantPrecise}


def _factory_gda_precise(model_type, **kwargs):
    try:
        if model_type == 'lda':
            kwargs["solver"] = "svd"
        return MODEL_TYPES_PRECISE[model_type.lower()](**kwargs)
    except Exception as _:
        raise Exception("Selected model does not exist")
