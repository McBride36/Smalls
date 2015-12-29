import json

class JSONDict(dict):
    def __init__(self, filename, **kwargs):
        super().__init__(**kwargs)
        self._filename = filename
        self.load_dict()

    def __setitem__(self, item, val):
        super().__setitem__(item.lower(), val)
        self.save_dict()
        
    def __getitem__(self, item):
        return super().__getitem__(item.lower())
        
    def __contains__(self, item):
        return super().__contains__(item.lower())

    def save_dict(self):
        with open(self._filename, "w") as f:
            data = json.dumps(dict(self.items()))
            f.write(data)

    def load_dict(self):
        try:
            with open(self._filename) as f:
                data = json.load(f)
                for k, v in data.items():
                    self[k] = v
        except FileNotFoundError:
            pass
