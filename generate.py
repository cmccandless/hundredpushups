import requests
import requests_cache
from lxml import html
import re
from json import dumps as json_dumps
import sys
import markdown_generator as mdg

requests_cache.install_cache()

TIME_PER_PUSHUP = 2  # seconds

BASE_URL = 'https://hundredpushups.com/'

RGX_NUMBER = re.compile('^(\d+)\+?$')
RGX_REST = re.compile(
    'rest (\d+) seconds between each set',
    flags=re.IGNORECASE
)
RGX_RULE = re.compile(
    '(\d+)-(\d+)|< (\d+)'
)


class PushupSetGroup(object):
    def __init__(self, rule, rest=0, sets=None):
        self.rule = rule
        self.rest = rest
        self.sets = sets or []

    def __in__(self, value):
        return value >= self.rule[0] and value <= self.rule[1]

    def __lt__(self, other):
        d = self.rule[0] - other.rule[0]
        if d != 0:
            return d < 0
        return self.rule[1] < other.rule[1]

    def estimate(self):
        return (
            sum(TIME_PER_PUSHUP * p for p in self.sets) +
            self.rest * (len(self.sets) - 1)
        )

    def __str__(self):
        return '{1}-{2} pushups: {0}+'.format(
            ', '.join(map(str, self.sets)),
            *self.rule
        )

    def json(self):
        return {
            'min': self.rule[0],
            'max': self.rule[1],
            'sets': self.sets
        }


class Day(object):
    def __init__(self, number=0, rest=0):
        self.number = number
        self.rest = rest
        self.set_groups = []

    def add_set_group(self, grp):
        self.set_groups.append(grp)
        self.set_groups.sort()

    def find_set_group(self, value):
        for grp in self.set_groups:
            if value in grp:
                return grp

    def estimate(self):
        return sum(
            grp.estimate()
            for grp in self.set_groups
        ) // len(self.set_groups) // 60

    def __str__(self):
        return '\n'.join([
            (
                f'Day {self.number} (rest {self.rest}s; '
                f'about {self.estimate()}min)'
            ),
            *map(str, self.set_groups)
        ])

    def json(self):
        return {
            'day_number': self.number,
            'rest': self.rest,
            'set_groups': [g.json() for g in self.set_groups]
        }


class Week(object):
    def __init__(self, number, days=None):
        self.number = number
        self.days = days or []

    def __str__(self):
        return '\n'.join([
            f'Week {self.number}',
            *map(str, self.days)
        ])

    def json(self):
        return {
            'week_number': self.number,
            'days': [d.json() for d in self.days]
        }


def get_week(n):
    url = '{}week{}.html'.format(BASE_URL, n)
    resp = requests.get(url)
    tree = html.fromstring(resp.content)

    week = Week(n)
    for table in tree.xpath('//table'):
        day = Day()
        for i, c in enumerate(table.xpath('thead/tr/th/text()')):
            if c.startswith('DAY'):
                day.number = int(c.split(' ')[1])
                continue
            m = RGX_REST.match(c)
            if m:
                day.rest = int(m.group(1))
                continue
        current_set = []
        for i, c in enumerate(table.xpath('tbody/tr/td/text()')):
            m = RGX_RULE.match(c)
            if m:
                if m.group(3):
                    rule = (0, int(m.group(3)))
                else:
                    rule = (
                        int(m.group(1)),
                        int(m.group(2))
                    )
                day.add_set_group(PushupSetGroup(rule, day.rest))
                continue
            if c.startswith('SET'):
                if current_set:
                    for count, s in zip(current_set, day.set_groups):
                        s.sets.append(count)
                current_set.clear()
                continue
            m = RGX_NUMBER.match(c)
            if m:
                current_set.append(int(m.group(1)))
                continue
        if current_set:
            for count, s in zip(current_set, day.set_groups):
                s.sets.append(count)
        week.days.append(day)
    return week


def create_json(weeks, filename):
    with open(filename, 'w') as f:
        f.write(json_dumps([w.json() for w in weeks], indent=2))


def create_md(weeks, filename):
    with open(filename, 'w') as f:
        writer = mdg.Writer(f)
        writer.write_heading('100 Pushups')
        writer.write('from ')
        writer.writeline(mdg.link(
            'https://hundredpushups.com',
            'hundredpushups.com'
        ))
        writer.writeline()

        writer.write_heading('Weeks', 2)
        writer.writeline()
        # unordered = mdg.List()
        # for i in range(1, 7):
        #     unordered.append(mdg.link(
        #         f'#week{i}',
        #         f'Week {i}'
        #     ))
        # writer.write(unordered)
        for i in range(1, 7):
            writer.write('- ')
            writer.writeline(mdg.link(
                f'#week-{i}',
                f'Week {i}'
            ))
            for j in range(1, 4):
                writer.write('  - ')
                writer.writeline(mdg.link(
                    f'#week-{i}-day-{j}',
                    f'Day {j}'
                ))
        writer.writeline()

        for i, week in enumerate(weeks, 1):
            writer.write_heading(f'Week {i}', 2)
            writer.writeline()
            for j, day in enumerate(week.days, 1):
                writer.write_heading(
                    f'Week {i}: Day {j}',
                    3
                )
                writer.writeline(f'Rest: {day.rest}s')
                writer.writeline()
                writer.writeline(f'Total: ~{day.estimate()}min')
                writer.writeline()
                table = mdg.Table()
                table.add_column('Pushups')
                for grp in day.set_groups:
                    table.add_column('{}-{}'.format(*grp.rule))
                rows = list(zip(*(grp.sets for grp in day.set_groups)))
                for k, row in enumerate(rows, 1):
                    if k < len(rows):
                        table.append(f'Set {k}', *row)
                    else:
                        table.append(
                            f'Set {k}',
                            *(f'{n}+' for n in row)
                        )
                writer.write(table)
                writer.writeline('---')
            if i in (2, 4):
                writer.writeline(mdg.strong(
                    'Do exhaustion test at the end of this week'
                ))
                writer.writeline('\n---')


if __name__ == '__main__':
    weeks = [get_week(i) for i in range(1, 7)]
    mode = '--print' if len(sys.argv) < 2 else sys.argv[1]
    filename = None if len(sys.argv) < 3 else sys.argv[2]
    if mode == '--print':
        for week in weeks:
            print(week)
    elif mode == '--json':
        create_json(weeks, filename or 'pushups.json')
    elif mode == '--md':
        create_md(weeks, filename or 'pushups.md')
