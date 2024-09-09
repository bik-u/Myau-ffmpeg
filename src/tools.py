"""
 For misc. data types needed in multiple other modules
"""


class Atrdict(dict):
    def __init__(self, iterable=None, **kwargs):
        if iterable:
            for name, item in iterable.items():
                if type(item) is dict:
                    item = Atrdict(item)
                self[name] = item

        for name, item in kwargs.items():
            self[name] = item

    def __getattribute__(self, name):
        if name in self:
            return self[name]
        else:
            # makes it work with external libs
            return super().__getattribute__(name)

    # adding dict values can be done by setting attribute
    def __setattr__(self, name, value):
        try:
            if type(value) is dict:
                value = Atrdict(value)

            self[name] = value

            return value
        except TypeError:
            return super().__setattr__(name, value)

    def get_safe(self, name, default=None):
        if name in self:
            return self[name]
        else:
            return default
