# Config rework tweaks

## Convert obsolete lists

Older assets write a list as a run of numbered tags:

```
category-era-0                        "1920s"
category-era-1                        "1930s"
category-era-2                        "1940s"
```

and the same list now reads as one tag with the elements between semicolons:

```
category-era                          "1920s;1930s;1940s"
```

**Tweaks > Convert obsolete lists** makes that change for every group in the text
on screen, keeps the values in the order the numbers say and the columns where
they stood, and ends with a message naming every tag it changed and every one it
left alone, with the reason. One press of Undo takes the whole change back.

A tag with `-number` on the end is changed when it stands on a line of its own
holding a quoted value. A run of them at one indent becomes one tag with the
values between semicolons; one standing on its own keeps its value and only loses
the number, because a list of one is still written as a single tag:

```
category-region-0                       "SE"
```

becomes

```
category-region                         "SE"
```

Nothing is touched when a value holds a `;` itself, or when the file already has
a tag of the plain name, or when another group of the same tags took that name
first - those are listed as left alone, with the reason. A `load0` or `camera0`
carries no dash, means something else entirely, and is never touched.

## Convert asset-filename to mesh-table

An older asset says which mesh it loads with a single tag:

```
asset-filename                          "MS_Shelter_4"
```

and the newer kind says the same thing with a container:

```
mesh-table
{
  default
  {
    mesh                                "MS_Shelter_4.im"
    auto-create                         1
  }
}
```

**Tweaks > Convert asset-filename to mesh-table** makes that change for every tag
in the text on screen: the tag goes, the container comes in at the indent the tag
stood at with its values on the same column as the rest of the file, and `.im`
goes on the end of the name - which is what the tag left off, and what a name
that already has it keeps once. The message afterwards names the mesh each new
container loads, and one press of Undo takes the whole of it back.

A file that already has a `mesh-table` is left exactly as it was, and the message
is a warning rather than a note: two containers would leave Trainz choosing
between two meshes. A tag that names no mesh - no value, empty quotes, a value
that is not in quotes, one running over several lines, or the tag itself used as
a container - is left where it is and listed with the reason.

## Remove language tags

An asset with text for several languages writes the same tag once per language:

```
description                             "casualwoman3"
description-de                          "Freizeit-Frau3"
description-ru                          "Прохожая3"
```

**Tweaks > Remove language tags** takes out every tag whose name ends in a dash
and two letters, the value with it, and leaves the plain `description` standing.
The message afterwards names every tag that went and says which one stayed, and
one press of Undo takes the whole sweep back.

The value goes with the tag however it is written: one on the line, one running
over several lines, or a whole container - its braces and everything inside
them, since that is its value. The two letters can be any two letters, because
the assets write `username-cn` and `username-jp` as often as they write the
proper `-zh` and `-ja`. A tag that is only spelled as if it were one, like
`contact-email` or a three-letter `description-eng`, is left alone, and so is a
tag whose value or container is never closed; that is said out loud rather than
cut into.

## Reorder tags

A chump file works with its tags in any order, but the ones Trainz writes have a
shape to them, and an asset edited by hand over ten years tends to lose it. **Tweaks
> Reorder tags** puts the top level tags back in that shape:

- `kuid` and then `username`, whatever was written above them;
- every tag that holds one value, in the order they were found;
- every container, in the order they were found;
- `kuid-table` and `obsolete-table` after all the other containers, when the file
  has them.

The same tidy-up reaches inside the containers, by a simpler rule: the tags
holding a value come first and the containers written beside them come after,
each keeping the order they were found in, at every depth of the file. Down there
no name is special, so a `kuid` written inside a sub-container stays where the
file put it.

```
kind                                    "interior"
mesh-table
{
  default
  {
    effects
    {
    }
    mesh                                "interior.im"
    auto-create                         1
  }
}
kuid                                    <kuid:79373:50023>
username                                "CFR interior"
obsolete-table
{
}
kuid-table
{
}
```

becomes

```
kuid                                    <kuid:79373:50023>
username                                "CFR interior"
kind                                    "interior"

mesh-table
{
  default
  {
    mesh                                "interior.im"
    auto-create                         1

    effects
    {
    }
  }
}

kuid-table
{
}

obsolete-table
{
}
```

On top of the order, a blank line separates a container from the line written
beside it, and nothing else: one under its closing `}` wherever another tag
follows it, and one above the line naming it wherever a tag stands there, however
deep inside the file the container sits, since those gaps are what show where one
container ends and the next one begins. None stands beside a brace - above another
`}` would drive a wedge between a tag and the container it is written inside, and
below a `{` would part a container from the brace it opens - and none at the start
or the end of the file, where there is nothing to separate. The rule is read both
ways, so a gap comes in where it is missing and comes out where the file has one
the rule does not ask for: a blank line between two tags that each hold one value,
a second blank line in a gap that one already says once, and a blank line inside a
container's braces. One gap between two containers serves the two of them. A blank
line written inside a value that runs over several lines belongs to that value and
is left where it is. The decoder puts those container gaps in when it expands a
`.chump`, so text coming from a `.chump` whose tags already stand in the order needs
nothing but the order; where its tags do not, a blank line travelling with a tag can
land between two tags, and comes out.
