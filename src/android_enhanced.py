import os
import platform
import re
import subprocess
from typing import Optional

try:
    # This fails when the code is executed directly and not as a part of python package installation,
    # I definitely need a better way to handle this.
    from androide.output_helper import print_message, print_error, print_error_and_exit, print_verbose
except ImportError:
    # This works when the code is executed directly.
    from output_helper import print_message, print_error, print_error_and_exit, print_verbose


_JAVA_VERSION_FOR_ANDROID = '1.8'
_JAVA8_INSTALL_COMMAND_FOR_MAC = 'brew cask install caskroom/versions/java8'
_SET_JAVA8_AS_DEFAULT_ON_MAC = 'export JAVA_HOME=$(/usr/libexec/java_home -v 1.8)'
_GET_ALL_JAVA_VERSIONS_ON_MAC = '/usr/libexec/java_home -V'
_GET_ALL_JAVA_VERSIONS_ON_LINUX = 'update-alternatives --display java'

_BUILD_TOOLS_REGEX = r'build-tools;\S*'
_SYSTEM_IMAGES_REGEX = 'system-images;android-([0-9]+);(.*);(.*)\n'


class AndroidEnhanced(object):

    def __init__(self) -> None:
        pass

    def run_doctor(self) -> None:
        print_message('Checking java version...')
        self._ensure_correct_java_version()
        print_message('Checking SDK manager is installed...')
        self._ensure_sdkmanager_is_installed()
        print_message('Checking that basic Android packages are installed...')
        if not self._ensure_basic_packages_are_installed():
            print_error_and_exit('Not all basic packages are installed')
    
    @staticmethod
    def _ensure_basic_packages_are_installed() -> bool:
        success = True
        installed_packages = AndroidEnhanced._get_installed_packages()
        basic_packages = AndroidEnhanced._get_basic_packages()
        n = len(basic_packages)
        for i in range(0, n):
            basic_package = basic_packages[i]
            if basic_package not in installed_packages:
                print_error('Basic packages \"%s\" is not installed' % basic_package)
                success = False
            else:
                print_message('Package %d/%d: \"%s\" is installed' % (i + 1, n, basic_package))

        return success

    def list_packages(self, arch=None, api_type=None) -> None:
        print_verbose('List packages(arch: %s, api_type: %s)' % (arch, api_type))
        if api_type is None:
            google_api_type = '.*?'
        else:
            google_api_type = 'api_type'

        if arch is None:
            arch_pattern = '.*?'
        else:
            arch_pattern = arch + '.*?'
        regex_pattern = 'system-images;android-([0-9]+);(%s);(%s)\n' % (google_api_type, arch_pattern)
        return_code, stdout, stderr = self._execute_cmd('sdkmanager --verbose --list --include_obsolete')
        system_images = re.findall(regex_pattern, stdout)
        arch_to_android_version_map = {}
        for system_image in system_images:
            android_api_version = system_image[0]
            google_api_type = system_image[1]
            arch = system_image[2]
            if google_api_type not in arch_to_android_version_map:
                arch_to_android_version_map[google_api_type] = {}
            if arch not in arch_to_android_version_map[google_api_type]:
                arch_to_android_version_map[google_api_type][arch] = []
            arch_to_android_version_map[google_api_type][arch].append(android_api_version)

        for (google_api_type, architectures) in arch_to_android_version_map.items():
            if google_api_type == 'default':
                print('Google API type: default (Standard Android image; no Google API)')
            else:
                print('Google API type: %s' % google_api_type)
            for arch in architectures:
                android_api_versions = arch_to_android_version_map[google_api_type][arch]
                print('%s -> %s' % (arch, ', '.join(android_api_versions)))
            print()

    def list_installed_packages(self):
        installed_packages = self._get_installed_packages()
        print('\n'.join(installed_packages))

    def list_avds(self):
        avd_manager = AndroidEnhanced._get_location_of_avd_manager()
        if not avd_manager:
            print_error_and_exit('avdmanager not found')
        cmd = '%s --verbose list avd' % avd_manager
        return_code, stdout, stderr = self._execute_cmd(cmd)
        if return_code != 0:
            print_error_and_exit('Failed to execute avdmanager')
        print(stdout)

    def install_api_version(self, version, arch=None, api_type=None) -> None:
        platform_package = self._get_platform_package(version)
        sources_package = self._get_sources_package(version)
        addons_package = self._get_add_ons_package(version, api_type)
        system_images_package = self._get_system_images_package(version, arch, api_type)

        package_list = list()
        package_list.append(platform_package)
        if sources_package:
            package_list.append(sources_package)
        if addons_package:
            package_list.append(addons_package)
        if system_images_package:
            package_list.append(system_images_package)
        if not self._install_sdk_packages(package_list):
            print_error_and_exit('Failed to install packages for api version: %s' % version)

    def list_build_tools(self):
        build_tools = self._get_build_tools()
        for build_tool in build_tools:
            print(build_tool)

    def list_others(self):
        return_code, stdout, stderr = self._execute_cmd('sdkmanager --verbose --list --include_obsolete')
        if return_code != 0:
            print_error_and_exit('Failed to list packages')

        print('Installed Packages:')
        lines = stdout.split('\n')
        for i in range(0, len(lines)):
            line = lines[i].strip()
            previous_line = None
            if i > 0:
                previous_line = lines[i - 1].strip()

            if not previous_line or previous_line.startswith('---'):
                is_package_name = True
            else:
                is_package_name = False

            if not is_package_name:
                continue

            print_verbose('Line is \"%s\" and previous line is \"%s\"' % (line, previous_line))

            if not line:
                continue
            elif line.startswith('system-images;') or line.startswith('platforms;') or line.startswith('sources;'):
                continue
            elif line.startswith('platform-tools'):
                continue
            elif line.startswith('build-tools;'):
                continue
            elif line.find('Info:') != -1:
                continue

            if line.endswith(':'):
                print('')
            print(line)

    def install_basic_packages(self):
        packages_to_install = self._get_basic_packages()
        if not self._install_sdk_packages(packages_to_install):
            print_error_and_exit('Failed to install basic packages')

    def update_all(self):
        return_code, stdout, stderr = self._execute_cmd('sdkmanager --update')
        if return_code != 0:
            print_error_and_exit('Failed to update, return code: %d' % return_code)
        count = 0
        if stdout:
            for line in stdout.split('\r'):
                if line.find('Fetch remote repository'):
                    continue
                else:
                    count += 1
        if count == 0:
            print_message('No packages to update')
            self._accept_all_licenses()
        else:
            print_message(stdout)

    @staticmethod
    def _ensure_correct_java_version():
        default_java_version = AndroidEnhanced._get_default_java_version()
        if default_java_version is None:
            print_error_and_exit('Java is not installed. Install Java for Android via %s' %
                                 _JAVA8_INSTALL_COMMAND_FOR_MAC)
        if default_java_version != _JAVA_VERSION_FOR_ANDROID:
            all_java_versions = AndroidEnhanced._get_all_java_versions()
            if _JAVA_VERSION_FOR_ANDROID in all_java_versions:
                print_error_and_exit('Java version %s is installed but default is set to Java %s.\n'
                                     'Set the correct java version via "%s"' % (
                                         _JAVA_VERSION_FOR_ANDROID,
                                         default_java_version,
                                         _SET_JAVA8_AS_DEFAULT_ON_MAC))
            else:
                print_error_and_exit('Java version is %s, Android needs Java %s.\n'
                                     'On Mac install it with "%s"\nAnd then set default version'
                                     'via "%s"' % (
                                         default_java_version, _JAVA_VERSION_FOR_ANDROID,
                                         _JAVA8_INSTALL_COMMAND_FOR_MAC, _SET_JAVA8_AS_DEFAULT_ON_MAC))
        else:
            print_message('Correct Java version %s is installed' % default_java_version)

    @staticmethod
    def _ensure_sdkmanager_is_installed():
        # Only works on Mac and GNU/Linux
        if AndroidEnhanced._on_linux() or AndroidEnhanced._on_mac():
            return_code, stdout, stderr = AndroidEnhanced._execute_cmd('command -v sdkmanager')
            if return_code != 0:
                print_error_and_exit('sdkamanger not found, is Android SDK installed? (return code: %d)' % return_code)

    @staticmethod
    def _accept_all_licenses():
        return_code, stdout, stderr = AndroidEnhanced._execute_cmd('yes | sdkmanager --licenses')
        if return_code != 0:
            print_error_and_exit('Failed to accept licenses, return code: %d' % return_code)
        license_regex = '([0-9]*) of ([0-9]*) SDK package licenses not accepted'
        result = re.search(license_regex, stdout)
        if result is None:
            print_message('All licenses accepted')
        else:
            print_message('%d of %d licenses accepted' % (int(result.group(1)), int(result.group(2))))

    @staticmethod
    def _get_default_java_version() -> Optional[str]:
        return_code, stdout, stderr = AndroidEnhanced._execute_cmd('java -version')
        java_version_regex = '"([0-9]+\.[0-9]+)\..*"'
        version = re.search(java_version_regex, stderr)
        if version is None:
            return None
        print_verbose('version object is %s' % version)
        return version.group(1)

    @staticmethod
    def _get_all_java_versions() -> [str]:
        if AndroidEnhanced._on_linux():
            return_code, stdout, stderr = AndroidEnhanced._execute_cmd(_GET_ALL_JAVA_VERSIONS_ON_LINUX)
            java_version_regex = 'java-([0-9]+.*?)/'
        elif AndroidEnhanced._on_mac():
            java_version_regex = r'"([0-9]+\.[0-9]+)\..*"'
            return_code, stdout, stderr = AndroidEnhanced._execute_cmd(_GET_ALL_JAVA_VERSIONS_ON_MAC)
        else:
            return []
        output = ''
        output += stdout
        output += stderr
        versions = re.findall(java_version_regex, output)
        versions = set(versions)
        print_verbose('Versions are %s' % versions)
        return versions
    
    @staticmethod
    def _get_installed_packages() -> [str]:
        # Don't pass --include_obsolete here since that seems to list all installed packages under obsolete
        # packages section as well.
        return_code, stdout, stderr = AndroidEnhanced._execute_cmd('sdkmanager --verbose --list --include_obsolete')
        start_line = 'Installed packages:'.lower()
        end_line = 'Available Packages:'.lower()
        lines = stdout.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i]
            if line.lower().find(start_line) != -1:
                i += 1
                break
            else:
                i += 1
        installed_packages = set()
        for j in range(i, len(lines)):
            line = lines[j]
            if line.lower().find(end_line) != -1:
                break
            line = line.strip()
            if not line:
                continue

            if line.startswith('----'):
                continue
            if line.startswith('Description:'):
                continue
            if line.startswith('Version:'):
                continue
            if line.startswith('Installed Location:'):
                continue
            if line.startswith('Installed Obsolete Packages:'):
                continue
            installed_packages.add(line)
        return sorted(installed_packages)

    @staticmethod
    def _get_build_tools() -> [str]:
        """
        :return: List of build tools packages, sorted by version number, latest package comes last
        """
        return_code, stdout, stderr = AndroidEnhanced._execute_cmd('sdkmanager --verbose --list --include_obsolete')
        if return_code != 0:
            print_error_and_exit('Failed to list build tools, stdout: %s, stderr: %s' % (stdout, stderr))
        build_tools = re.findall(_BUILD_TOOLS_REGEX, stdout)
        build_tools = sorted(build_tools)
        print_verbose('Build tools are %s' % build_tools)
        return build_tools

    @staticmethod
    def _get_basic_packages() -> [str]:
        build_tools = AndroidEnhanced._get_build_tools()
        if not build_tools:
            print_error_and_exit('Build tools list is empty, this is unexpected')
        latest_build_package = build_tools[-1]
        print_verbose('Latest build package is \"%s\"' % latest_build_package)
        packages_to_install = [
            latest_build_package,
            'emulator',
            'tools',
            'platform-tools',
            'extras;android;m2repository',
            'extras;google;m2repository',
            'patcher;v4',
        ]
        # HAXM is not required on Linux. It is required on Windows and OSX.
        # I am assuming that this tool will never run on anything except Windows and OSX.
        # I don't know whether HAXM is required on BSD or not.
        if not AndroidEnhanced._on_linux():
            packages_to_install.append('extras;intel;Hardware_Accelerated_Execution_Manager')
        return packages_to_install

    @staticmethod
    def _get_platform_package(version) -> str:
        return 'platforms;android-%s' % version

    @staticmethod
    def _get_sources_package(version) -> Optional[str]:
        try:
            version = int(version)
            if version < 14:
                print_error('Sources are not available before API 14')
                return None
        except ValueError:
            pass

        return 'sources;android-%s' % version

    @staticmethod
    def _get_add_ons_package(version, api_type) -> Optional[str]:
        # addons package is gone going forward. It was present only on these versions.
        if api_type == 'google_apis' and version in [15, 16, 17, 18, 19, 21, 22, 23, 24]:
            return 'add-ons;addon-google_apis-google-%s' % version
        # Note: There are two more packages types, GDK for Glass and Google TV which is deprecated.
        # No point, supporting them here.
        # add-ons;addon-google_gdk-google-19
        # add-ons;addon-google_tv_addon-google-12
        # add-ons;addon-google_tv_addon-google-13
        return None

    @staticmethod
    def _get_system_images_package(version, arch, api_type) -> Optional[str]:
        try:
            version = int(version)
            if version < 10:
                print_verbose('System images are bundled in the platform below API 10')
                return None
            # API 24 onwards, for x86, prefer to install google_apis_playstore image
            # then google_apis image. It seems it is a better image.
            if version >= 24 and api_type == 'google_apis' and arch == 'x86':
                api_type = 'google_apis_playstore'
                return 'system-images;android-%s;%s;%s' % (version, api_type, arch)
            # API 28 onwards, for x86_64, prefer to install google_apis_playstore image
            # then google_apis image. It seems it is a better image.
            if version >= 28 and api_type == 'google_apis' and arch == 'x86_64':
                api_type = 'google_apis_playstore'
                return 'system-images;android-%s;%s;%s' % (version, api_type, arch)
        except ValueError:
            pass
        return 'system-images;android-%s;%s;%s' % (version, api_type, arch)

    def _install_sdk_packages(self, package_names) -> bool:
        for package_name in package_names:
            exists = self._does_package_exist(package_name)
            if not exists:
                print_message('Package \"%s\" not found' % package_name)
                return False

        print_message('Installing packages [%s]...' % ', '.join(package_names))
        package_names_str = '\"' + '\" \"'.join(package_names) + '\"'
        return_code, stdout, stderr = self._execute_cmd('yes | sdkmanager --verbose %s' % package_names_str)
        if return_code != 0:
            print_error('Failed to install packages \"%s\"' % ' '.join(package_names))
            print_error('Stderr is \n%s' % stderr)
            return False
        return True

    @staticmethod
    def _get_location_of_avd_manager() -> Optional[str]:
        sdk_location = AndroidEnhanced._get_location_of_android_sdk()
        if not sdk_location:
            return None
        return os.path.join(sdk_location, 'tools', 'bin', 'avdmanager')

    @staticmethod
    def _get_location_of_android_sdk() -> Optional[str]:
        try:
            return os.environ['ANDROID_SDK_ROOT']
        except KeyError:
            print_error_and_exit(
                'Set ANDROID_SDK_ROOT environment variable to point to Android SDK root')

        process = subprocess.Popen(
            'realpath $(dirname $(readlink $(command -v sdkmanager)))/../..',
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        if process.returncode != 0:
            print_verbose('Android SDK not found, return code: %d' % process.returncode)
            return None
        return stdout.decode('utf-8').strip()

    # TODO(ashishb): Implement this in the future to check whether a package is available or not.
    def _does_package_exist(self, package_name):
        return True

    @staticmethod
    def _execute_cmd(cmd) -> (int, str, str):
        """
        :param cmd: Command to be executed
        :return: (returncode, stdout, stderr)
        """
        print_verbose('Executing command: %s' % cmd)
        process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        stdout = ''
        stderr = ''

        while process.poll() is None:
            line1 = process.stdout.readline()
            line1 = line1.decode('utf-8').strip()
            if line1:
                stdout += (line1 + '\n')
                print_verbose(line1)

            line2 = process.stderr.readline()
            line2 = line2.decode('utf-8').strip()
            if line2:
                stderr += (line2 + '\n')
                print_verbose(line2)

        leftover_stdout, leftover_stderr = process.communicate()
        leftover_stdout = leftover_stdout.decode('utf-8').strip()
        leftover_stderr = leftover_stderr.decode('utf-8').strip()
        for line in leftover_stdout.split('\n'):
            line = line.strip()
            if line:
                print_verbose(line)
                stdout += (line + '\n')

        for line in leftover_stderr.split('\n'):
            line = line.strip()
            if line:
                stderr += (line + '\n')
                print_verbose(line)

        return process.returncode, stdout, stderr

    @staticmethod
    def _on_linux():
        return platform.system() == 'Linux'

    @staticmethod
    def _on_mac():
        return platform.system() == 'Darwin'

    @staticmethod
    def _is_64bit_architecture():
        return platform.architecture()[0] == '64bit'
