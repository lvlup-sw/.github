// Minimal C# source for the CodeQL reusable-workflow canary.
//
// CodeQL's `csharp` extractor at `build-mode: none` performs buildless
// extraction over .cs sources — a single source file is enough to produce a
// database and exercise init + analyze end to end. The canary runs with
// `upload: never`, so this fixture only needs to be syntactically valid C#;
// no real finding is asserted (the canary proves the reusable runs, not that
// any specific query fires).

namespace Lvlup.Ci.CodeqlCanary;

internal static class Program
{
    private static int Add(int a, int b) => a + b;

    private static void Main()
    {
        System.Console.WriteLine(Add(2, 3));
    }
}
