import xml.etree.ElementTree as et
import csv
from colorsys import hsv_to_rgb
import statistics
import copy
import numpy

from sklearn.utils.validation import check_is_fitted

from base_classes import Object, Context
from speech_module import SpeechModule
from re_generator_v2 import REG

class CorpusTraining:
    def __init__(self):
        # self.Theta = p_threshold
        w2c = "data/w2c_4096.txt"
        self.sm = SpeechModule(w2c)
        self.reg = REG()
        self.workspaces = {}

    def save_models(self):
        self.reg.save_models()

    def get_train_x_y(self, xml_workspace_filename, csv_responses_filename):
        self.parse_workspace_data_from_xml(xml_workspace_filename)

        responses = self.parse_responses_from_csv(csv_responses_filename)
        tokenized_responses = self.process_all_outputs(responses)
        print("training_v2.py:28: len(tokenized_responses) = ", len(tokenized_responses))

        feature_inputs = self.assemble_x(tokenized_responses)
        # TODO update to work with all responses (rather than one per qid)
        feature_outputs = self.assemble_Y(tokenized_responses)
        # raise NotImplementedError

        return feature_inputs, feature_outputs

    def train(self, feature_inputs, feature_outputs, save=True):
        i = numpy.array(feature_inputs)
        o = numpy.array(feature_outputs[:len(feature_inputs)])
        print(i.shape, o.shape)
        self.reg.train_model(i, o)
        if save:
            self.reg.save_models()

    def parse_workspace_data_from_xml(self, filename):
        self.tree = et.parse(filename)
        self.root = self.tree.getroot() # data (elements are workspaces)

        for ws in self.root:
            id = ws.attrib["id"]
            obj_lst = []
            key_item = None

            for item in ws:
                feature_dict = {}
                item_id = item.attrib["id"]

                for datum in item:
                    if datum.tag == "type":
                         feature_dict["type"] = datum.text
                    elif datum.tag == "hsv":
                        # parse as tuple
                        # print(datum.text.split(', '))
                        h, s, v = [float(x) for x in datum.text.split(', ')]
                        # normalize from gimp conventions to [0, 1] range
                        h /= 360.0
                        s /= 100.0
                        v /= 100.0
                        rgb = hsv_to_rgb(h, s, v)
                        feature_dict["rgb"] = [255 * d for d in rgb]
                    elif datum.tag == "location":
                        x = int(datum[0].text)
                        y = int(datum[1].text)
                        feature_dict[datum.tag] = (x, y)
                    elif datum.tag == "dimensions":
                        feature_dict["dim"] = (int(datum[0].text), int(datum[1].text))

                o = Object()
                o.from_dict(feature_dict)
                if item_id == "KEY":
                    key_item = o

                obj_lst.append(o)

            # print(obj_lst)
            self.workspaces[id] = (key_item, Context(obj_lst))

    def assemble_x_for_q(self, obj, context, tokenized_response):
        """UPDATED"""
        labels, tokens = tokenized_response
        type = obj.get_feature_val("type")

        features = ["color", "size", "dim"]

        xq = []

        for t in tokens:
            x, _, results = self.reg.get_model_input(obj, context)
            xq.append(x)

            if t == self.sm.COLOR_I:
                kept = results["color"]
                features.remove("color")
            elif t == self.sm.SIZE_I:
                kept = results["size"]
                features.remove("size")
            elif t == self.sm.DIM_I:
                kept = results["dim"]
                features.remove("dim")

            context = self.reg.update_context(kept)

        # you'll always have a last one pre-noun
        if not tokens or features:
            x, _, _ = self.reg.get_model_input(obj, context)
            xq.append(x)
        return xq

    def assemble_x(self, tokenized_responses):
        """ UPDATED """
        X = []
        index = 0
        iter_count = 0
        for ws in self.workspaces:
            obj, context = self.workspaces[ws]
            for pid_response in tokenized_responses[index]:
                xq = self.assemble_x_for_q(obj, context, pid_response)
                X+=xq
                iter_count += 1
            index+=1
        print("x iterations", iter_count)
        return X

    def test_labeling(self, key, c):
        # show usage
        # key, env = self.workspaces['Q3.2']
        # c = Context(env)
        w2c = "data/w2c_4096.txt"
        self.sm = SpeechModule(w2c)
        clr = self.sm.label_feature(key, c, "color")
        sz = self.sm.label_feature(key, c, "size")
        dim = self.sm.label_feature(key, c, "dim")

        # print(clr, sz, dm)
        return clr, sz, dim

    def parse_responses_from_csv(self, filename):
        with open(filename) as csvfile:
            csvreader = csv.reader(csvfile, delimiter=",")
            header = next(csvreader)

            qs_to_indicies = {}
            indicies_to_qs = {}

            # get field names from first row
            for i in range(len(header)):
                field = header[i]
                # print(field)
                if field[0] == "Q":
                    indicies_to_qs[i] = field
                    qs_to_indicies[field] = i

            row = next(csvreader)
            row = next(csvreader)
            all_responses = [[] for x in qs_to_indicies.keys()]

            for row in csvreader:
                count = 0
                for index in indicies_to_qs.keys():
                    response = row[index]
                    if response: # check response is not empty
                    # add response to appropriate list
                        all_responses[count].append(response)
                        count += 1

        print(all_responses)
        return all_responses

    def assemble_Y(self, tokenized_responses):
        """ UPDATED """
        Y = []
        iter_count=0
        for qid in tokenized_responses:
            for labels, tokens in qid:
                Yq = self.assemble_Y_for_q(tokens)
                Y += Yq
                iter_count+=1
        print("Y_iterations",iter_count)
        return Y

    def assemble_Y_for_q(self, tokenized_response):
        """ UPDATED """
        Yq = []

        base = [self.sm.COLOR_I, self.sm.SIZE_I, self.sm.DIM_I]
        features = copy.copy(base)
        for token in tokenized_response:
            if token == self.sm.COLOR_I:
                Yq.append("color")
            elif token == self.sm.SIZE_I:
                Yq.append("size")
            elif token == self.sm.DIM_I:
                Yq.append("dim")

            features.remove(token)

        # last pre-noun space
        if not tokenized_response or features:
            Yq.append("none")
        return Yq

    def process_all_outputs(self, all_responses):
        # NEW VERSION: use all responses (requires data cleaning)
        parsed_responses = []
        for qid in all_responses:
            qid_y = []
            for r in qid:
                labels, tokens = self.sm.process_speech_string(r)
                qid_y.append((labels, tokens))
            parsed_responses.append(qid_y)
        return parsed_responses

if __name__ == "__main__":
    trainer = CorpusTraining()
    xml_file = "data/stim_v1_original.xml"
    csv_file = "data/study_v1_responses.csv"

    xml2_file = "data/stim_v2.xml"
    csv2_file = "data/study_v2_responses.csv"

    inputs, outputs = trainer.get_train_x_y(xml_file, csv_file)
    trainer.workspaces = {}
    inputs2, outputs2 = trainer.get_train_x_y(xml2_file, csv2_file)
    # #
    # responses = [["screwdriver", "blue screwdriver"], ["bottle", "red bottle"]]
    #
    # tokenized = trainer.process_all_outputs(responses)
    # trainer.parse_workspace_data_from_xml(xml_file)
    # # #
    # inputs = trainer.assemble_x(tokenized)
    # outputs = trainer.assemble_Y(tokenized)

    i = inputs + inputs2
    o = outputs + outputs2

    trainer.train(i, o)
