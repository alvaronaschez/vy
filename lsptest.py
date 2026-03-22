

def foo(a: list[str]) -> None:
    for x in a:
        print(x)


# a: list[str] = []
# for x in range(10):
#     a.append(str(x))
a = []
for x in range(10):
    a.append(x)

foo(a)
