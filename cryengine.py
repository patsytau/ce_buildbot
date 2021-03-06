from buildbot.plugins import *

CMAKE_GENERATORS = {'win_x86': 'Visual Studio 14 2015',
                    'win_x64': 'Visual Studio 14 2015 Win64',
                    'linux_x64_gcc': 'Unix Makefiles',
                    'linux_x64_clang': 'Unix Makefiles'}


@util.renderer
def compute_build_properties(props):
    """
    Set the build properties required by the target, for instance; the path to the toolchain file.
    :param props: Current build properties.
    """

    # This ugly construction works around (by effectively hard-coding) a problem with 'buildbot try' whereby
    # the project property wasn't being set. Other properties were, so it's likely a problem with the way
    # I've written the 'Try' scheduler.
    project = props.getProperty('project')
    if not project:
        project = 'CRYENGINE'

    build_properties = {
        'project': project,
        'cmakegenerator': CMAKE_GENERATORS.get(props.getProperty('target'))
    }

    if props.getProperty('target') == 'win_x86':
        build_properties.update({
            'vsplatform': 'Win32',
            'cmake_sln_tag': 'Win32',
            'toolchain_path': 'Tools/CMake/toolchain/windows/WindowsPC-MSVC.cmake',
            'rm_sdklink_cmd': r'if exist {proj}\Code\SDKs rmdir {proj}\Code\SDKs'.format(proj=project),
            'mk_sdklink_cmd': r'mklink /J {proj}\Code\SDKs ce_sdks'.format(proj=project)
        })
    elif props.getProperty('target') == 'win_x64':
        build_properties.update({
            'vsplatform': 'x64',
            'cmake_sln_tag': 'Win64',
            'toolchain_path': 'Tools/CMake/toolchain/windows/WindowsPC-MSVC.cmake',
            'rm_sdklink_cmd': r'if exist {proj}\Code\SDKs rmdir {proj}\Code\SDKs'.format(proj=project),
            'mk_sdklink_cmd': r'mklink /J {proj}\Code\SDKs ce_sdks'.format(proj=project)
        })
    elif props.getProperty('target') == 'linux_x64_gcc':
        build_properties.update({
            'toolchain_path': 'Tools/CMake/toolchain/linux/Linux_GCC.cmake',
            'rm_sdklink_cmd': ['rm', '{}/Code/SDKs'.format(project)],
            'mk_sdklink_cmd': ['ln', '-s', 'ce_sdks', '{}/Code/SDKs'.format(project)]
        })
    elif props.getProperty('target') == 'linux_x64_clang':
        build_properties.update({
            'toolchain_path': 'Tools/CMake/toolchain/linux/Linux_Clang.cmake',
            'rm_sdklink_cmd': ['rm', '{}/Code/SDKs'.format(project)],
            'mk_sdklink_cmd': ['ln', '-sfn', 'ce_sdks', '{}/Code/SDKs'.format(project)]
        })
    return build_properties


def add_common_steps(factory):
    """
    Add steps to the provided factory that are common to both Windows and Linux builds.
    :param factory: Factory to which the steps should be added.
    """
    factory.addStep(steps.SetProperties(properties=compute_build_properties))

    # Remove pre-existing link to avoid Code/SDKs being blown away by the 'get code' step.
    factory.addStep(steps.ShellCommand(name='unlink dependencies',
                                       command=util.Property('rm_sdklink_cmd'),
                                       warnOnFailure=True))

    factory.addStep(steps.Git(name='get code',
                              timeout=3600,
                              repourl=util.Interpolate('git@%(prop:repository)s'),
                              branch=util.Interpolate('%(prop:branch)s'),
                              workdir=util.Interpolate('build/%(prop:project)s')))

    # If dependencies are in a git repository, they should use Git LFS. Note that the initial clone is very
    # slow when using buildbot's git step. It is better to manually run 'git lfs clone ...' manually on the slave first.
    factory.addStep(steps.Git(name='get dependencies',
                              timeout=3600,
                              alwaysUseLatest=True,
                              repourl=util.Interpolate('git@%(prop:sdk_repo_url)s'),
                              branch=util.Interpolate('%(prop:branch)s'),
                              workdir=util.Interpolate('build/ce_sdks')))

    # Link dependencies are symlinked rather than used as a submodule in case multiple repositories are intended
    # to be built. As a submodule this would result in multiple copies of the SDKs being stored on the machine.
    factory.addStep(steps.ShellCommand(name='link dependencies',
                                       command=util.Property('mk_sdklink_cmd')))

    factory.addStep(steps.CMake(name='configure',
                                path=util.Interpolate('../%(prop:project)s'),
                                generator=util.Interpolate('%(prop:cmakegenerator)s'),
                                options=[util.Interpolate('-DCMAKE_TOOLCHAIN_FILE=%(prop:toolchain_path)s')],
                                workdir=util.Interpolate('build/%(prop:target)s_%(prop:config)s')))


def get_compile_win_factory():
    factory = util.BuildFactory()
    add_common_steps(factory)

    # Actually compile the binaries. We need the 'cmake_sln_tag' since the solutions are named slightly
    # differently to the platform for 64-bit Windows: 'Win64' rather than 'x64'.
    factory.addStep(steps.MsBuild14(mode='build',
                                    platform=util.Interpolate('%(prop:vsplatform)s'),
                                    config=util.Interpolate('%(prop:config)s'),
                                    projectfile=util.Interpolate('CryEngine_CMake_%(prop:cmake_sln_tag)s.sln'),
                                    workdir=util.Interpolate('build/%(prop:target)s_%(prop:config)s')))
    return factory
