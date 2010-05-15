#-*- coding:utf-8 -*-

import re
from functools import wraps
from contextlib import contextmanager

from stemming.porter2 import stem
from flask import Response, request


def compound2affixes(compound):
    c = r'[bcdfgjklmnprstvxz]'
    v = r'[aeiou]'
    cc = r'''(?:bl|br|
                cf|ck|cl|cm|cn|cp|cr|ct|
                dj|dr|dz|fl|fr|gl|gr|
                jb|jd|jg|jm|jv|kl|kr|
                ml|mr|pl|pr|
                sf|sk|sl|sm|sn|sp|sr|st|
                tc|tr|ts|vl|vr|xl|xr|
                zb|zd|zg|zm|zv)'''
    vv = r'(?:ai|ei|oi|au)'
    rafsi3v = r"(?:%(cc)s%(v)s|%(c)s%(vv)s|%(c)s%(v)s'%(v)s)" % locals()
    rafsi3 = r'(?:%(rafsi3v)s|%(c)s%(v)s%(c)s)' % locals()
    rafsi4 = r'(?:%(c)s%(v)s%(c)s%(c)s|%(cc)s%(v)s%(c)s)' % locals()
    rafsi5 = r'%(rafsi4)s%(v)s' % locals()
    
    for i in xrange(1, len(compound)/3+1):
        reg = r'(?:(%(rafsi3)s)([nry])??|(%(rafsi4)s)(y))' % locals() * i
        reg2 = r'^%(reg)s(%(rafsi3v)s|%(rafsi5)s)$$' % locals()
        matches = re.findall(reg2, compound, re.VERBOSE)
        if matches:
            return [r for r in matches[0] if r]
    
    return []


def tex2html(tex):
    """Turn most of the TeX used in jbovlaste into HTML.
    
    >>> tex2html('$x_1$ is $10^2*2$ examples of $x_{2}$.')
    u'x<sub>1</sub> is 10<sup>2\\xd72</sup> examples of x<sub>2</sub>.'
    >>> tex2html('\emph{This} is emphasised and \\\\textbf{this} is boldfaced.')
    u'<em>This</em> is emphasised and <strong>this</strong> is boldfaced.'
    """
    def math(m):
        t = []
        for x in m.group(1).split('='):
            x = x.replace('{', '').replace('}', '')
            x = x.replace('*', u'×')
            if '_' in x:
                t.append(u'%s<sub>%s</sub>' % tuple(x.split('_')[0:2]))
            elif '^' in x:
                t.append(u'%s<sup>%s</sup>' % tuple(x.split('^')[0:2]))
            else:
                t.append(x)
        return '='.join(t)
    def typography(m):
        if m.group(1) == 'emph':
            return u'<em>%s</em>' % m.group(2)
        elif m.group(1) == 'textbf':
            return u'<strong>%s</strong>' % m.group(2)
    def lines(m):
        format = '\n%s'
        if m.group(1).startswith('|'):
            format = '\n<span style="font-family: monospace">    %s</span>'
        elif m.group(1).startswith('>'):
            format = '\n<span style="font-family: monospace">   %s</span>'
        return format % m.group(1)
    def puho(m):
        format = 'inchoative\n<span style="font-family: monospace">%s</span>'
        return format % m.group(1)
    tex = re.sub(r'\$(.+?)\$', math, tex)
    tex = re.sub(r'\\(emph|textbf)\{(.+?)\}', typography, tex)
    tex = re.sub(r'(?![|>\-])\s\s+(.+)', lines, tex)
    tex = re.sub(r'inchoative\s\s+(----.+)', puho, tex)
    return tex

def braces2links(text, entries):
    """Turns {quoted words} into HTML links.
    
    >>> import db
    >>> braces2links('See also {mupli}.', db.entries)
    u'See also <a href="mupli" title="x<sub>1</sub> is
    an example/sample/specimen/instance/case/illustration of
    common property(s) x<sub>2</sub> of set x<sub>3</sub>.">mupli</a>.'
    >>> braces2links('See also {missing}.', db.entries)
    u'See also <a
    href="http://jbovlaste.lojban.org/dict/addvalsi.html?valsi=missing"
    title="This word is missing, please add it!" class="missing">missing</a>.'
    """
    def f(m):
        try:
            values = (m.group(1), entries[m.group(1)].definition, m.group(1))
            return u'<a href="%s" title="%s">%s</a>' % values
        except KeyError:
            link = [u'<a href="']
            link.append(u'http://jbovlaste.lojban.org')
            link.append(u'/dict/addvalsi.html?valsi=%s"')
            link.append(u' title="This word is missing, please add it!"')
            link.append(u' class="missing">%s</a>')
            return ''.join(link) % (m.group(1), m.group(1))
    return re.sub(r'\{(.+?)\}', f, text)


def add_stems(token, collection, item):
    stemmed = stem(token.lower())
    if stemmed not in collection:
        collection[stemmed] = []
    if item not in collection[stemmed]:
        collection[stemmed].append(item)


def etag(app):
    """Decorator to add ETag handling to a callback."""
    def decorator(f):
        @wraps(f)
        def wrapper(**kwargs):
            response = app.make_response(f(**kwargs))
            response.set_etag(app.etag)
            if not app.debug:
                response.make_conditional(request)
            return response
        return wrapper
    return decorator


@contextmanager
def ignore(exc):
    """Context manager to ignore an exception."""
    try:
        yield
    except exc:
        pass


# http://mwh.geek.nz/2009/04/26/python-damerau-levenshtein-distance/
def dameraulevenshtein(seq1, seq2):
    """Calculate the Damerau-Levenshtein distance between sequences.

    This distance is the number of additions, deletions, substitutions,
    and transpositions needed to transform the first sequence into the
    second. Although generally used with strings, any sequences of
    comparable objects will work.

    Transpositions are exchanges of *consecutive* characters; all other
    operations are self-explanatory.

    This implementation is O(N*M) time and O(M) space, for N and M the
    lengths of the two sequences.

    >>> dameraulevenshtein('ba', 'abc')
    2
    >>> dameraulevenshtein('fee', 'deed')
    2

    It works with arbitrary sequences too:
    >>> dameraulevenshtein('abcd', ['b', 'a', 'c', 'd', 'e'])
    2
    """
    # codesnippet:D0DE4716-B6E6-4161-9219-2903BF8F547F
    # Conceptually, this is based on a len(seq1) + 1 * len(seq2) + 1 matrix.
    # However, only the current and two previous rows are needed at once,
    # so we only store those.
    oneago = None
    thisrow = range(1, len(seq2) + 1) + [0]
    for x in xrange(len(seq1)):
        # Python lists wrap around for negative indices, so put the
        # leftmost column at the *end* of the list. This matches with
        # the zero-indexed strings and saves extra calculation.
        twoago, oneago, thisrow = oneago, thisrow, [0] * len(seq2) + [x + 1]
        for y in xrange(len(seq2)):
            delcost = oneago[y] + 1
            addcost = thisrow[y - 1] + 1
            subcost = oneago[y - 1] + (seq1[x] != seq2[y])
            thisrow[y] = min(delcost, addcost, subcost)
            # This block deals with transpositions
            if (x > 0 and y > 0 and seq1[x] == seq2[y - 1]
                and seq1[x-1] == seq2[y] and seq1[x] != seq2[y]):
                thisrow[y] = min(thisrow[y], twoago[y - 2] + 1)
    return thisrow[len(seq2) - 1]


if __name__ == '__main__':
    import doctest
    doctest.testmod(optionflags=doctest.NORMALIZE_WHITESPACE)

